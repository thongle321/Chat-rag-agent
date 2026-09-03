"""Products catalog — ChatGPT-style recommendations grounded on real SKUs.

- SQL table `products` (single-tenant, see models/unified.py)
- search_products(): embedding cosine rank over active products (small catalog,
  computed on the fly — no separate Chroma collection needed)
- ProductSource adapter: Shopify + CSV + manual (both CSV option and online)
"""

from __future__ import annotations

import csv
import io
import logging
import math
from typing import Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.embeddings import get_embeddings
from app.db.session import async_session_factory
from app.models.unified import Product

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------
def to_dict(p: Product) -> dict:
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
    dot = sum(x * y for x, y in zip(a, b))
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
        from app.db.embeddings import query_prefix as _qp

        q_emb = next(get_embeddings().query_embed(_qp() + query))
        texts = [_product_text(p) for p in rows]
        # FastEmbed passage embed for products
        from app.db.embeddings import passage_prefix as _pp

        p_embs = list(get_embeddings().embed([_pp() + t for t in texts]))
        scored = sorted(
            zip(rows, [_cosine(q_emb, e) for e in p_embs], strict=True),
            key=lambda x: x[1],
            reverse=True,
        )
        out = []
        for p, score in scored[:k]:
            # Gate weak matches — strict grounding: don't recommend irrelevant SKUs
            if score < 0.15:
                continue
            d = to_dict(p)
            d["score"] = round(float(score), 4)
            out.append(d)
        logger.info("product search q=%r n=%d kept=%d", query[:60], len(rows), len(out))
        return out
    except Exception:
        logger.exception("product embedding search failed, falling back to LIKE")
        ql = query.lower()
        out = []
        for p in rows:
            hay = f"{p.name} {p.description or ''} {p.category or ''}".lower()
            if any(t in hay for t in ql.split() if len(t) > 2):
                out.append(to_dict(p))
            if len(out) >= k:
                break
        return out


async def list_products(active_only: bool = True) -> list[dict]:
    async with async_session_factory() as db:
        stmt = select(Product)
        if active_only:
            stmt = stmt.where(Product.is_active.is_(True))
        rows = (await db.execute(stmt.order_by(Product.created_at.desc()))).scalars().all()
        return [to_dict(p) for p in rows]


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
        for p in data.get("products", []):
            variants = p.get("variants", [{}])
            v0 = variants[0] if variants else {}
            img = (p.get("image") or {}).get("src") or (
                p.get("images", [{}])[0].get("src") if p.get("images") else None
            )
            out.append(
                {
                    "name": p.get("title", ""),
                    "description": (p.get("body_html") or "")[:2000],
                    "price": float(v0.get("price") or 0) or None,
                    "currency": "USD",
                    "image_url": img,
                    "product_url": None,
                    "category": p.get("product_type") or None,
                    "stock": sum(int(v.get("inventory_quantity") or 0) for v in variants),
                    "sku": v0.get("sku") or None,
                    "source": "shopify",
                    "external_id": str(p.get("id")),
                }
            )
        return out


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


async def upsert_products(items: list[dict], db: AsyncSession) -> int:
    """Upsert by (source, external_id) or sku. Returns count."""
    n = 0
    for it in items:
        stmt = None
        if it.get("source") and it.get("external_id"):
            stmt = select(Product).where(Product.source == it["source"], Product.external_id == str(it["external_id"]))
        elif it.get("sku"):
            stmt = select(Product).where(Product.sku == it["sku"])
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
