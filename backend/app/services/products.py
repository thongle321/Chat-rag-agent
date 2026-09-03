"""Products catalog — ChatGPT-style recommendations grounded on real SKUs.

- SQL table `products` (single-tenant, see models/unified.py)
- search_products(): embedding cosine rank over active products (small catalog,
  computed on the fly — no separate Chroma collection needed)
- ProductSource adapter: Shopify + CSV + manual (both CSV option and online)
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import math
from typing import Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.embeddings import get_embeddings, passage_prefix, query_prefix
from app.db.session import async_session_factory
from app.models.unified import Product

logger = logging.getLogger(__name__)

# Minimum embedding cosine to recommend a SKU — strict grounding gate.
PRODUCT_SCORE_GATE = 0.30


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------
def product_to_dict(p: Product) -> dict:
    price = float(p.price) if p.price is not None else None
    return {
        "id": p.id,
        "sku": p.sku,
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
    if p.sku:
        parts.append(f"SKU: {p.sku}")
    return "\n".join(parts)


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


# ---------------------------------------------------------------------------
# Search — embedding rank over active products, strict grounding
# ---------------------------------------------------------------------------
async def search_products(query: str, k: int = 6, category: str | None = None) -> list[dict]:
    """Return top-k active products ranked by embedding cosine. Empty = no match."""
    async with async_session_factory() as db:
        stmt = select(Product).where(Product.is_active.is_(True))
        if category:
            stmt = stmt.where(Product.category == category)
        rows = (await db.execute(stmt)).scalars().all()
    if not rows:
        return []
    try:
        # FastEmbed is blocking — offload like Chroma/BM25 (AGENTS.md Gotchas)
        q_emb = await asyncio.to_thread(lambda: next(get_embeddings().query_embed(query_prefix() + query)))
        texts = [_product_text(p) for p in rows]
        p_embs = await asyncio.to_thread(lambda: list(get_embeddings().embed([passage_prefix() + t for t in texts])))
        scored = sorted(
            zip(rows, [_cosine(q_emb, e) for e in p_embs], strict=False),
            key=lambda x: x[1],
            reverse=True,
        )
        # Gate BEFORE slicing so weak top-k entries don't waste slots.
        out = []
        for prod, score in scored:
            if score < PRODUCT_SCORE_GATE:
                break
            d = product_to_dict(prod)
            d["score"] = round(float(score), 4)
            out.append(d)
            if len(out) >= k:
                break
        logger.info("product search q=%r n=%d kept=%d", query[:60], len(rows), len(out))
        return out
    except Exception:
        logger.exception("product embedding search failed, falling back to LIKE")
        tokens = [t for t in query.lower().split() if len(t) > 2]
        need = 2 if len(tokens) > 1 else 1  # LIKE fallback honors grounding: multi-word needs 2 hits
        out = []
        for prod in rows:
            hay = f"{prod.name} {prod.description or ''} {prod.category or ''}".lower()
            if sum(1 for t in tokens if t in hay) >= need:
                out.append(product_to_dict(prod))
            if len(out) >= k:
                break
        return out


async def list_products(active_only: bool = True) -> list[dict]:
    async with async_session_factory() as db:
        stmt = select(Product)
        if active_only:
            stmt = stmt.where(Product.is_active.is_(True))
        rows = (await db.execute(stmt.order_by(Product.created_at.desc()))).scalars().all()
        return [product_to_dict(p) for p in rows]


# ---------------------------------------------------------------------------
# ProductSource adapter — Shopify first, CSV fallback (both supported)
# ---------------------------------------------------------------------------
class ProductSource(Protocol):
    async def fetch_products(self) -> list[dict]: ...


class ShopifySource:
    """Fetch products via Shopify Admin API.

    Needs: shop_domain (e.g. mystore.myshopify.com) + admin access token.
    """

    def __init__(self, shop_domain: str, access_token: str):
        self.shop_domain = shop_domain.strip().replace("https://", "").replace("http://", "").rstrip("/")
        self.access_token = access_token

    async def fetch_products(self) -> list[dict]:
        url = f"https://{self.shop_domain}/admin/api/2025-01/products.json?limit=250"
        headers = {"X-Shopify-Access-Token": self.access_token}
        async with httpx.AsyncClient(timeout=30) as cli:
            r = await cli.get(url, headers=headers)
            r.raise_for_status()
            data = r.json()
        out = []
        for item in data.get("products", []):
            variants = item.get("variants", [{}])
            v0 = variants[0] if variants else {}
            handle = item.get("handle")
            out.append(
                {
                    "name": item.get("title", ""),
                    "description": (item.get("body_html") or "")[:2000],
                    "price": float(v0.get("price") or 0) or None,
                    "currency": "USD",
                    "image_url": _shopify_image(item),
                    # Storefront URL so Buy works for synced SKUs (was None)
                    "product_url": f"https://{self.shop_domain}/products/{handle}" if handle else None,
                    "category": item.get("product_type") or None,
                    "stock": sum(int(v.get("inventory_quantity") or 0) for v in variants),
                    "sku": v0.get("sku") or None,
                    "source": "shopify",
                    "external_id": str(item.get("id")),
                }
            )
        return out


def _shopify_image(item: dict) -> str | None:
    """Extract primary image URL without chained .get() navigation."""
    primary = item.get("image") or {}
    if primary.get("src"):
        return primary["src"]
    for img in item.get("images") or []:
        if img.get("src"):
            return img["src"]
    return None


class CsvSource:
    """CSV content as a ProductSource so both ingest paths share the interface."""

    def __init__(self, content: str):
        self.content = content

    async def fetch_products(self) -> list[dict]:
        return parse_csv(self.content)


def parse_csv(content: str) -> list[dict]:
    """CSV columns: name,description,price,currency,image_url,product_url,category,stock,sku."""
    reader = csv.DictReader(io.StringIO(content))
    out = []
    for row in reader:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        try:
            price = float(row.get("price") or 0) or None
        except ValueError:
            price = None
        try:
            stock = int(float(row.get("stock") or 0))
        except ValueError:
            stock = 0
        out.append(
            {
                "name": name,
                "description": (row.get("description") or "")[:2000] or None,
                "price": price,
                "currency": (row.get("currency") or "USD").strip() or "USD",
                "image_url": (row.get("image_url") or "") or None,
                "product_url": (row.get("product_url") or "") or None,
                "category": (row.get("category") or "") or None,
                "stock": stock,
                "sku": (row.get("sku") or "") or None,
                "source": "csv",
                "external_id": None,
            }
        )
    return out


def _dedupe_stmt(it: dict):
    """Single key-fn for upsert identity: (source, external_id) → sku → name."""
    if it.get("source") and it.get("external_id"):
        return select(Product).where(Product.source == it["source"], Product.external_id == str(it["external_id"]))
    if it.get("sku"):
        return select(Product).where(Product.sku == it["sku"])
    if it.get("name"):
        # CSV rows without sku/external_id previously always inserted — dedupe by name,
        # scoped to source so a CSV row can't collide with a Shopify SKU of the same name.
        if it.get("source"):
            return select(Product).where(Product.source == it["source"], Product.name == it["name"])
        return select(Product).where(Product.name == it["name"])
    return None


async def upsert_products(items: list[dict], db: AsyncSession) -> int:
    """Upsert by (source, external_id) → sku → name. Returns count."""
    n = 0
    for it in items:
        stmt = _dedupe_stmt(it)
        existing = (await db.execute(stmt)).scalar_one_or_none() if stmt is not None else None
        if existing:
            for k in ("name", "description", "price", "currency", "image_url", "product_url", "category", "stock"):
                if it.get(k) is not None:
                    setattr(existing, k, it[k])
            existing.is_active = True
        else:
            db.add(Product(**{k: v for k, v in it.items() if k in Product.__table__.columns.keys()}))
        n += 1
    await db.commit()
    return n


async def sync_source(source: ProductSource, db: AsyncSession) -> int:
    items = await source.fetch_products()
    return await upsert_products(items, db)
