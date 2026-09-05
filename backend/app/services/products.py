"""Products catalog — ChatGPT-style recommendations grounded on real catalog rows.

- SQL table `products` is the system of record (single-tenant, see models/unified.py)
- `products` Chroma collection is the search index: CRUD write-through sync
  (sync_product_to_index / remove_product_from_index), search_products() ranks
  via hybrid RRF + distance gate and hydrates display fields from chunk metadata
- ProductSource adapter: CSV + manual ingest (Shopify Global Catalog is live-only, never saved)
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import re
from typing import Annotated, Protocol

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.embeddings import get_embeddings, passage_prefix, query_prefix
from app.db.session import async_session_factory
from app.db.vector_store import fuse_ranks as _fuse
from app.db.vector_store import get_product_store
from app.models.unified import Product

logger = logging.getLogger(__name__)

# Maximum Chroma cosine distance for a recommendation — strict grounding gate.
# (Old SQL-scan gate was cosine similarity >= 0.30; distance = 1 - similarity.)
PRODUCT_DISTANCE_GATE = 0.70

# Metadata fields round-tripped through the index: _chunk_meta writes them,
# search_products reads them back. Add a field once, here.
_DISPLAY_FIELDS = (
    "name",
    "description",
    "price",
    "currency",
    "image_url",
    "product_url",
    "category",
    "stock",
    "source",
    "external_id",
)

# Budget hints like "under $30" / "$10 max" feed the analyzer regex-fallback
# (max_price pre-gate). Bare "$N" is deliberately NOT a ceiling ("2 for $10?",
# "$8 over budget").
_BUDGET_RE = re.compile(
    r"(?:under|below|max|up to|<=|<)\s*\$?\s*(\d+(?:\.\d+)?)"
    r"|\$?\s*(\d+(?:\.\d+)?)\s*(?:max|or less)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------
def product_to_dict(p: Product) -> dict:
    price = float(p.price) if p.price is not None else None
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "price": price,
        "currency": p.currency or "USD",
        "image_url": p.image_url,
        "product_url": p.product_url,
        "category": p.category,
        "stock": p.stock,
        "is_active": p.is_active,
        "source": p.source,
        "external_id": p.external_id,
    }


def _product_text(p: Product) -> str:
    parts = [p.name or ""]
    if p.category:
        parts.append(f"Category: {p.category}")
    if p.description:
        parts.append(p.description)
    return "\n".join(parts)


def product_chunk_id(pid: str) -> str:
    return f"product:{pid}"


def _chunk_meta(p: Product) -> dict:
    """Display fields for the index (Chroma metadata: str/int/float/bool, no Nones)."""
    meta: dict = {
        "product_id": p.id,
        "name": p.name or "",
        "currency": p.currency or "USD",
        "stock": int(p.stock or 0),
        "is_active": True,
    }
    if p.description:
        meta["description"] = p.description[:2000]
    if p.price is not None:
        meta["price"] = float(p.price)
    if p.image_url:
        meta["image_url"] = p.image_url
    if p.product_url:
        meta["product_url"] = p.product_url
    if p.category:
        meta["category"] = p.category
    if p.source:
        meta["source"] = p.source
    if p.external_id:
        meta["external_id"] = p.external_id
    return meta


async def sync_products_to_index(products: list[Product]) -> None:
    """CRUD write-through: upsert active rows, drop inactive ones. Never raises —
    SQL already committed by the caller; an index failure only logs loudly (Q8)."""
    upserts = [p for p in products if p.is_active]
    drops = [product_chunk_id(p.id) for p in products if not p.is_active]
    try:
        store = get_product_store()
        if drops:
            await asyncio.to_thread(store.delete_ids, drops)
        if upserts:
            texts = [_product_text(p) for p in upserts]
            embs = await asyncio.to_thread(lambda: list(get_embeddings().embed([passage_prefix() + t for t in texts])))
            await asyncio.to_thread(
                store.upsert,
                [product_chunk_id(p.id) for p in upserts],
                embs,
                texts,
                [_chunk_meta(p) for p in upserts],
            )
    except Exception:
        logger.exception("product index sync failed (%d upserts, %d drops)", len(upserts), len(drops))


async def remove_product_from_index(pid: str) -> None:
    try:
        await asyncio.to_thread(get_product_store().delete_ids, [product_chunk_id(pid)])
    except Exception:
        logger.exception("product index delete failed pid=%s", pid)


def format_usd(price: float | int | None, currency: str | None = "USD") -> str:
    """Whole-dollar USD display ('$399'); other currencies fall back to 'N CODE'."""
    if price is None:
        return "price on request"
    if (currency or "USD").upper() == "USD":
        return f"${float(price):,.0f}"
    return f"{float(price):,.0f} {(currency or '').upper()}"


def _parse_budget(query: str) -> float | None:
    """Extract a price ceiling from hints like 'under $30' / '$10 max'. None = no signal."""
    m = _BUDGET_RE.search(query)
    if not m:
        return None
    try:
        return float(m.group(1) or m.group(2))
    except (TypeError, ValueError):
        return None


def _rerank(query: str, scored: list[tuple[dict, float]]) -> list[tuple[dict, float]]:
    """Deterministic re-rank over GATE-passing hits (existing columns only).

    Sort key (desc): in-stock first, then category word-overlap with the
    query, then fusion score. No price leg: max_price already pre-gates,
    so re-deriving a regex budget here was tautological.
    Stable sort preserves fusion order within ties.
    """
    qtokens = {t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2}

    def key(item: tuple[dict, float]) -> tuple[int, int, float]:
        prod, score = item
        in_stock = 1 if (prod.get("stock") or 0) > 0 else 0
        if prod.get("category"):
            ctokens = {t for t in re.findall(r"[a-z0-9]+", prod["category"].lower()) if len(t) > 2}
            cat_ok = 1 if (ctokens & qtokens) else 0
        else:
            cat_ok = 0
        return (in_stock, cat_ok, score)

    return sorted(scored, key=key, reverse=True)


# ---------------------------------------------------------------------------
# Search — embedding rank over active products, strict grounding
# ---------------------------------------------------------------------------
async def search_products(
    query: str,
    k: int = 6,
    category: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """Return top-k active products ranked by the products vector collection. Empty = no match.

    Hybrid RRF (dense over-retrieve + BM25 ranks) + cosine-distance gate, then
    category/max_price post-filters on chunk metadata (priceless rows excluded
    when gated). Display fields hydrate from the index — SQL is never scanned.
    """
    if not query.strip():
        return []
    try:
        store = get_product_store()
        # FastEmbed/Chroma/BM25 are blocking — offload (AGENTS.md Gotchas)
        q_emb = await asyncio.to_thread(lambda: next(get_embeddings().query_embed(query_prefix() + query)))
        over = settings.retrieval_bm25_overretrieve
        # Category pushes into the dense side (pre-fusion); the Python post-filter
        # below still guards BM25-only strays. max_price stays post-filter so
        # priceless rows are excluded with explicit semantics.
        where = {"category": category} if category else None
        vec_hits = await asyncio.to_thread(store.query, q_emb, k * over, where)
        if not vec_hits:
            return []
        dist_by_id = {h["id"]: h["score"] for h in vec_hits}
        vec_ranks = [h["id"] for h in vec_hits]
        bm25_ranks = await asyncio.to_thread(store.bm25_ranks, query, k * over)
        fused = _fuse(vec_ranks, bm25_ranks, k=settings.retrieval_rrf_k)
        gated = [(doc_id, sc) for doc_id, sc in fused if dist_by_id.get(doc_id, 2.0) < PRODUCT_DISTANCE_GATE]
        if not gated:
            logger.info("product search q=%r kept=0 (gated)", query[:60])
            return []
        hydrated = {h["id"]: h["metadata"] for h in await asyncio.to_thread(store.fetch, [i for i, _ in gated])}
        scored = []
        for doc_id, score in gated:
            m = hydrated[doc_id]
            if category and m.get("category") != category:
                continue
            price = m.get("price")
            if max_price is not None and (not isinstance(price, (int, float)) or price > max_price):
                continue
            d = {"id": m["product_id"], "is_active": True, "score": round(float(score), 4)}
            for f in _DISPLAY_FIELDS:
                d[f] = m.get(f)
            scored.append((d, score))
        out = [d for d, _ in _rerank(query, scored)[:k]]
        logger.info("product search q=%r kept=%d", query[:60], len(out))
        return out
    except Exception:
        logger.exception("product vector search failed")
        return []


async def list_products(active_only: bool = True) -> list[dict]:
    async with async_session_factory() as db:
        stmt = select(Product)
        if active_only:
            stmt = stmt.where(Product.is_active.is_(True))
        rows = (await db.execute(stmt.order_by(Product.created_at.desc()))).scalars().all()
        return [product_to_dict(p) for p in rows]


# ---------------------------------------------------------------------------
# ProductSource adapter — CSV ingest (manual CRUD bypasses it)
# ---------------------------------------------------------------------------
class ProductSource(Protocol):
    async def fetch_products(self) -> list[dict]: ...


class CsvSource:
    """CSV content as a ProductSource so both ingest paths share the interface."""

    def __init__(self, content: str):
        self.content = content
        self.skipped = 0  # rows rejected by feed hygiene (populated on fetch)

    async def fetch_products(self) -> list[dict]:
        items, skipped = parse_csv_stats(self.content)
        self.skipped = skipped
        if skipped:
            logger.warning("CSV import rejected %d rows missing name/price", skipped)
        return items


def parse_csv(content: str) -> list[dict]:
    """CSV columns: name,description,price,currency,image_url,product_url,category,stock."""
    items, _ = parse_csv_stats(content)
    return items


def _coerce_stock(v) -> int:
    """Stock tolerates float-strings ('3.0') and garbage (→ 0, row still imports)."""
    try:
        return int(float(v)) if v is not None else 0
    except (TypeError, ValueError):
        return 0


class ProductCsvRow(BaseModel):
    """One CSV import row — name + price required, everything else optional."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=500)
    description: str | None = None
    price: float
    currency: str = "USD"
    image_url: str | None = None
    product_url: str | None = None
    category: str | None = None
    stock: Annotated[int, BeforeValidator(_coerce_stock)] = 0

    @field_validator("description", mode="before")
    @classmethod
    def _truncate_description(cls, v):
        return v[:2000] if isinstance(v, str) else v


def parse_csv_stats(content: str) -> tuple[list[dict], int]:
    """Parse CSV rows, rejecting feed-hygiene failures.

    Rows missing name or price are skipped (imageless/priceless cards never
    render). image_url is optional — imageless rows import and render text-only.
    Returns (items, skipped_count).
    """
    reader = csv.DictReader(io.StringIO(content))
    out = []
    skipped = 0
    for row in reader:
        # Drop blank cells so unset columns fall back to model defaults.
        data = {k: v for k, v in row.items() if k and (v or "").strip()}
        try:
            item = ProductCsvRow.model_validate(data)
        except ValidationError:
            skipped += 1
            continue
        out.append({**item.model_dump(), "source": "csv", "external_id": None})
    return out, skipped


def _dedupe_stmt(it: dict):
    """Single key-fn for upsert identity: (source, external_id) → name."""
    if it.get("source") and it.get("external_id"):
        return select(Product).where(Product.source == it["source"], Product.external_id == str(it["external_id"]))
    if it.get("name"):
        # CSV rows without external_id previously always inserted — dedupe by name,
        # scoped to source so a CSV row can't collide with a Shopify product of the same name.
        if it.get("source"):
            return select(Product).where(Product.source == it["source"], Product.name == it["name"])
        return select(Product).where(Product.name == it["name"])
    return None


async def upsert_products(items: list[dict], db: AsyncSession) -> int:
    """Upsert by (source, external_id) → name. Commits, then write-through syncs the index. Returns count."""
    n = 0
    synced: list[Product] = []
    for it in items:
        stmt = _dedupe_stmt(it)
        existing = (await db.execute(stmt)).scalar_one_or_none() if stmt is not None else None
        if existing:
            for k in (
                "name",
                "description",
                "price",
                "currency",
                "image_url",
                "product_url",
                "category",
                "stock",
            ):
                if it.get(k) is not None:
                    setattr(existing, k, it[k])
            existing.is_active = True
            synced.append(existing)
        else:
            p = Product(**{k: v for k, v in it.items() if k in Product.__table__.columns.keys()})
            db.add(p)
            synced.append(p)
        n += 1
    await db.commit()
    for p in synced:  # re-attach post-commit (attributes expire) before reading fields
        await db.refresh(p)
    await sync_products_to_index(synced)
    return n


async def sync_source(source: ProductSource, db: AsyncSession) -> int:
    items = await source.fetch_products()
    return await upsert_products(items, db)
