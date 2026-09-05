"""Shopify Global Catalog MCP over direct HTTPS (no MCP client library).

`POST https://catalog.shopify.com/api/ucp/mcp` — plain JSON-RPC `tools/call`
with `search_catalog`, authenticated by the `meta.ucp-agent.profile` URL alone
(Anonymous tier, no API key). See docs/research/shopify-global-catalog.md.

Results are live-search only — Shopify's usage rules forbid caching results or
re-using images, so nothing here is ever persisted.
"""

from __future__ import annotations

import asyncio
import heapq
import html
import json
import logging
import re
import uuid

import httpx2 as httpx
import logfire
import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.embeddings import cosine_sim, get_embeddings, passage_prefix, query_prefix

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://catalog.shopify.com/api/ucp/mcp"
DEFAULT_PROFILE_URL = "https://shopify.dev/ucp/agent-profiles/2026-08-25/valid-with-capabilities.json"

KEY_ENABLED = "shopify_catalog_enabled"
KEY_ENDPOINT = "shopify_catalog_endpoint"
KEY_PROFILE_URL = "shopify_catalog_profile_url"
KEY_CATALOG_ID = "shopify_catalog_id"

_TAG_RE = re.compile(r"<[^>]+>")


class GlobalCatalogError(Exception):
    """Friendly Global Catalog failure (unreachable, bad profile, bad query)."""


async def get_catalog_config(session: AsyncSession) -> dict:
    """Admin-saved MCP connection. Enabled only when explicitly turned on."""
    res = await session.execute(
        text("SELECT setting_key, value_plain FROM app_settings WHERE setting_key LIKE 'shopify_catalog_%'")
    )
    kv = {k: (v or "") for k, v in res.fetchall()}
    return {
        "enabled": kv.get(KEY_ENABLED, "") == "1",
        "endpoint": kv.get(KEY_ENDPOINT, "") or DEFAULT_ENDPOINT,
        "profile_url": kv.get(KEY_PROFILE_URL, "") or DEFAULT_PROFILE_URL,
        "catalog_id": kv.get(KEY_CATALOG_ID, ""),
    }


async def save_catalog_config(session: AsyncSession, data: dict) -> dict:
    for k in (KEY_ENABLED, KEY_ENDPOINT, KEY_PROFILE_URL, KEY_CATALOG_ID):
        if data.get(k) is None:
            continue
        v = str(data[k])
        exists = await session.execute(text("SELECT id FROM app_settings WHERE setting_key=:k"), {"k": k})
        if exists.fetchone():
            await session.execute(
                text(
                    "UPDATE app_settings SET value_plain=:v, value_encrypted=NULL,"
                    " updated_at=CURRENT_TIMESTAMP WHERE setting_key=:k"
                ),
                {"v": v, "k": k},
            )
        else:
            await session.execute(
                text("INSERT INTO app_settings (id, setting_key, value_plain) VALUES (:id,:k,:v)"),
                {"id": uuid.uuid4().hex[:36], "k": k, "v": v},
            )
    await session.commit()
    return await get_catalog_config(session)


async def _rpc(endpoint: str, method: str, params: dict, timeout: float = 30.0) -> dict:
    try:
        async with httpx.AsyncClient(timeout=timeout) as cli:
            r = await cli.post(
                endpoint,
                headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
                json={"jsonrpc": "2.0", "method": method, "id": 1, "params": params},
            )
    except httpx.ConnectError:
        raise GlobalCatalogError("Could not reach the Shopify catalog API — check the endpoint URL.") from None
    if r.status_code == 429:
        raise GlobalCatalogError("Catalog rate limit hit (429). Wait a minute and retry.")
    if r.status_code >= 400 and r.status_code != 422:
        raise GlobalCatalogError(f"Catalog request failed (HTTP {r.status_code}).")
    try:
        body = r.json()
    except ValueError:
        raise GlobalCatalogError("Catalog returned a non-JSON response.") from None
    if body.get("error"):
        err = body["error"] or {}
        code, msg = err.get("code"), (err.get("message") or "unknown error")[:300]
        if code == -32001:
            msg += " — the agent profile URL is unreachable or declares no catalog capability."
        raise GlobalCatalogError(f"Catalog error: {msg}")
    return body.get("result") or {}


async def test_catalog(endpoint: str, profile_url: str) -> list[str]:
    """Admin 'connect' check: tools/list must advertise search_catalog."""
    result = await _rpc(
        endpoint or DEFAULT_ENDPOINT,
        "tools/list",
        {"arguments": {"meta": {"ucp-agent": {"profile": profile_url or DEFAULT_PROFILE_URL}}}},
        timeout=15.0,
    )
    tools = [t.get("name", "") for t in result.get("tools", []) if isinstance(t, dict)]
    if "search_catalog" not in tools:
        raise GlobalCatalogError("Catalog connected but does not offer search_catalog.")
    return tools


def _plain_text(value: dict | None, limit: int = 500) -> str | None:
    if not value:
        return None
    raw = value.get("plain") or value.get("html")
    if not raw:
        return None
    text = html.unescape(_TAG_RE.sub(" ", raw))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] or None


def _major(amount: int | float | None) -> float | None:
    return (amount / 100) if isinstance(amount, (int, float)) else None


def _pick_variant(variants: list[dict]) -> dict:
    """Cheapest available offer first — the buy box for the recommendation card."""
    avail = [v for v in variants if (v.get("availability") or {}).get("available")]
    pool = avail or variants

    def _price(v: dict) -> float:
        p = (v.get("price") or {}).get("amount")
        return float(p) if isinstance(p, (int, float)) else float("inf")

    return min(pool, key=_price) if pool else {}


def _map_product(p: dict) -> dict:
    variants = [v for v in (p.get("variants") or []) if isinstance(v, dict)]
    best = _pick_variant(variants)
    price = best.get("price") or {}
    media = [m for m in (p.get("media") or []) if m.get("type") == "image" and m.get("url")]
    seller = best.get("seller") or {}
    rating = p.get("rating") or {}
    # Live search hits often omit the canonical product page `url` — fall back to
    # the variant checkout URL so cards stay clickable (merchant site, item in cart).
    product_url = p.get("url") or best.get("checkout_url")
    return {
        "id": p.get("id") or best.get("id") or "",
        "name": p.get("title") or "Untitled product",
        "description": _plain_text(p.get("description")),
        "price": _major(price.get("amount")),
        "currency": price.get("currency") or "USD",
        "image_url": media[0]["url"] if media else None,
        "product_url": product_url,
        "checkout_url": best.get("checkout_url"),
        "category": None,
        "stock": None,
        "available": bool((best.get("availability") or {}).get("available")),
        "seller": seller.get("name"),
        "seller_domain": seller.get("domain"),
        "rating": rating.get("value"),
        "source": "shopify-global",
    }


async def _rerank_local(query: str, prods: list[dict], k: int) -> list[dict]:
    """Order Shopify candidates by e5 cosine against the query, keep top-k.

    Fail-open: on embedding failure Shopify's own ordering stands (sliced)."""
    if not prods:
        return prods
    try:
        texts = [f"{p.get('name') or ''}\n{p.get('description') or ''}" for p in prods]

        def _embed() -> tuple[np.ndarray, list[np.ndarray]]:
            model = get_embeddings()
            q = np.asarray(next(model.query_embed(query_prefix() + query)))
            ps = [np.asarray(e) for e in model.embed([passage_prefix() + t for t in texts])]
            return q, ps

        q_emb, p_embs = await asyncio.to_thread(_embed)
        ranked = heapq.nlargest(
            min(k, len(prods)),
            ((p, cosine_sim(q_emb, e)) for p, e in zip(prods, p_embs, strict=True)),
            key=lambda x: x[1],
        )
        return [{**p, "score": round(score, 4)} for p, score in ranked]
    except Exception:
        logger.exception("global catalog re-rank failed, keeping Shopify order")
        return prods[:k]


async def search_global_catalog(
    query: str,
    limit: int = 6,
    *,
    fetch_limit: int = 50,
    endpoint: str = DEFAULT_ENDPOINT,
    profile_url: str = DEFAULT_PROFILE_URL,
    catalog_id: str = "",
    currency: str = "USD",
    country: str = "US",
) -> list[dict]:
    """Live-search the Global Catalog, then locally cosine re-rank to `limit`.

    Fetch-wide/curate-locally: Shopify ranks the full catalog, we pull the top
    `fetch_limit` candidates and order them by e5 cosine against the query.
    Never persisted (Shopify usage rules).
    """
    if not query.strip():
        return []
    limit = max(1, min(limit, 50))
    fetch_limit = max(limit, min(fetch_limit, 50))
    catalog: dict = {
        "query": query.strip(),
        "filters": {"available": True},
        "context": {"address_country": country, "currency": currency},
        "pagination": {"limit": fetch_limit},
    }
    if catalog_id:
        catalog["catalog_id"] = catalog_id
    result = await _rpc(
        endpoint,
        "tools/call",
        {
            "name": "search_catalog",
            "arguments": {"meta": {"ucp-agent": {"profile": profile_url}}, "catalog": catalog},
        },
    )
    content = result.get("structuredContent") or {}
    products = [p for p in (content.get("products") or []) if isinstance(p, dict)]
    out = [_map_product(p) for p in products]
    out = await _rerank_local(query, out, limit)
    # DEBUG: dump the full raw JSON response to the backend console.
    print(json.dumps(result, indent=1, ensure_ascii=False, default=str), flush=True)
    # logfire.info (not logger.info): stdlib records are swallowed by the
    # LogfireLoggingHandler console, while spans print like `chat.message logged`.
    logfire.info(
        "shopify.catalog search",
        query=query[:120],
        hits=len(out),
    )
    for p in out:
        logfire.info(
            "shopify.catalog hit",
            name=p["name"][:120],
            price=p["price"],
            currency=p["currency"],
            seller=p.get("seller") or "",
            url=p.get("product_url") or "",
        )
    return out
