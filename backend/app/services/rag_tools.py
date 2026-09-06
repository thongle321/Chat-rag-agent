"""Thin retrieval tools for the task agents. No prompts, no loops.

Each tool retrieves, formats context for the model, and stashes
citation/product accumulators on Deps. Imported by the runner's
per-task agent assembly.
"""

import asyncio
import logging

from pydantic_ai import RunContext

from app.db.session import async_session_factory
from app.services.products import _parse_budget, format_usd
from app.services.products import search_products as _search_products
from app.services.rag_routing import Deps, _resolve_shopping_filters
from app.services.shopify_global import GlobalCatalogError, get_catalog_config
from app.services.shopify_global import search_global_catalog as _search_global

logger = logging.getLogger(__name__)


def _format_context(docs: list[dict], nums: list[int]) -> str:
    if not docs:
        return "(No relevant documents found.)"
    parts = []
    for d, n in zip(docs, nums, strict=True):
        meta = d["metadata"]
        title = meta.get("clean_title") or "document"
        page = meta.get("page")
        if page is None:
            page = meta.get("chunk")
        page_str = f", p.{page + 1}" if page is not None else ""
        ref = meta.get("reference")
        ref_str = f" (Ref: {ref})" if ref else ""
        parts.append(f"[{n}] {title}{ref_str}{page_str}\n{d['content']}")
    return "\n\n".join(parts)


def _track_sources(deps: Deps, docs: list[dict]) -> list[int]:
    """Register deduplicated citation metadata; return the source number per chunk."""
    nums = []
    for d in docs:
        meta = d["metadata"]
        title = meta.get("clean_title") or "document"
        ref = meta.get("reference")
        entry = next(
            (s for s in deps.retrieved if s["title"] == title and s.get("reference") == ref),
            None,
        )
        if entry is None:
            entry = {
                "n": len(deps.retrieved) + 1,
                "id": d.get("id", ""),
                "title": title,
                "reference": ref,
                "pages": [],
            }
            deps.retrieved.append(entry)
        nums.append(entry["n"])
        page = meta.get("page")
        # ponytail: chunk index stands in for page until real page metadata exists at ingest
        if page is None:
            page = meta.get("chunk")
        if page is not None and page + 1 not in entry["pages"]:
            entry["pages"].append(page + 1)
    return nums


async def search_documents(ctx: RunContext[Deps], query: str) -> str:
    """Search the private knowledge base and return relevant document excerpts.

    Call this when the question may relate to the stored documents, including
    follow-ups (formulate a standalone query yourself). Do NOT call it for
    greetings, small talk, or questions about the assistant itself.

    Args:
        query: A standalone, self-contained search question.
    """
    docs = await asyncio.to_thread(ctx.deps.retrieval.search, query, 8)
    if not docs:
        return "(No relevant documents found.)"
    nums = _track_sources(ctx.deps, docs)
    return _format_context(docs, nums)


def _format_products(prods: list[dict], start: int = 0) -> str:
    if not prods:
        return "(No matching products in catalog.)"
    lines = []
    for i, p in enumerate(prods, start + 1):
        price = format_usd(p.get("price"), p.get("currency"))
        stock = f", stock {p.get('stock', 0)}" if p.get("stock") is not None else ""
        seller = f", sold by {p['seller']}" if p.get("seller") else ""
        line = f"[P{i}] {p['name']} — {price}{stock}{seller} (id: {p['id']})"
        # Shopify-only: hand the LLM the clickable URL; local rows stay as-is.
        if p.get("source") == "shopify-global":
            url = p.get("product_url") or p.get("checkout_url")
            if url:
                line += f" — link: {url}"
        lines.append(line)
    return "\n".join(lines)


async def search_products(ctx: RunContext[Deps], query: str) -> str:
    """Search the e-commerce product catalog and return matching products.

    Call this IMMEDIATELY when the user asks for recommendations, shopping
    advice, what to buy/eat/use, or anything that could map to a product —
    even when the query is vague (e.g. 'good headphones?'). Never interrogate
    first: recommend what comes back. Pass the user's raw query through; price
    and category extraction is handled for you. ONLY recommend products
    returned here — never invent products. If no match, say so in one short line
    and ask at most ONE follow-up question (budget or category).

    Args:
        query: A standalone product search (e.g. 'spicy lunch under $10').
    """
    category, max_price, search_text = await _resolve_shopping_filters(
        ctx.deps.model, query, _parse_budget(query), prefetch=ctx.deps.analysis
    )
    prods = await _search_products(search_text, 6, category=category, max_price=max_price)
    ctx.deps.products = prods
    ctx.deps.products_searched = True
    return _format_products(prods)


async def search_shopify_catalog(ctx: RunContext[Deps], query: str) -> str:
    """Search Shopify's Global Catalog — live products from millions of merchants.

    Call this when search_products returned no match, or when the user wants
    wider choice beyond the local catalog ('anywhere', 'online', brand names we
    don't carry). Results are live and never saved. Cite them exactly like local
    products ([P1] [P2] in order). If not connected, it says so — then skip it.

    Args:
        query: A standalone product search (e.g. 'trail running shoes under $150').
    """
    try:
        async with async_session_factory() as db:
            cfg = await get_catalog_config(db)
    except Exception:
        logger.warning("catalog config read failed", exc_info=True)
        return "(Shopify catalog is not connected.)"
    if not cfg.get("enabled"):
        return "(Shopify catalog is not connected — only local products available.)"
    try:
        prods = await _search_global(
            query,
            6,
            endpoint=cfg["endpoint"],
            profile_url=cfg["profile_url"],
            catalog_id=cfg.get("catalog_id", ""),
        )
    except GlobalCatalogError:
        logger.warning("global catalog search failed", exc_info=True)
        return "(Shopify catalog search failed — recommend from local products only.)"
    except Exception:
        logger.exception("global catalog search crashed")
        return "(Shopify catalog search failed — recommend from local products only.)"
    ctx.deps.products = [*ctx.deps.products, *prods]
    ctx.deps.products_searched = True
    if not prods:
        return "(No matching products in the Shopify catalog.)"
    return _format_products(prods, start=len(ctx.deps.products) - len(prods))
