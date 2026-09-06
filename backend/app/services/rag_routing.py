"""Intent routing + shopping-filter resolution for the answer runner.

Owns the shared run types (Deps, QueryFilters) so the tools and runner
modules both import from here — imports flow one way, no cycles.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent
from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.unified import Product
from app.prompts import ANALYZER_PROMPT
from app.retrieval import get_retrieval

logger = logging.getLogger(__name__)


@dataclass
class Deps:
    """Runtime deps injected into the graph per-run. Swap in fakes for tests."""

    model: Any
    model_name: str
    retrieval: Any = None
    retrieved: list[dict] = field(default_factory=list)
    products: list[dict] = field(default_factory=list)
    products_searched: bool = False
    analysis: "QueryFilters | None" = None

    def __post_init__(self):
        if self.retrieval is None:
            self.retrieval = get_retrieval()


class QueryFilters(BaseModel):
    """Analyzer output: intent + shopping filters extracted from a raw user query."""

    intent: str = "docs"
    category: str | None = None
    max_price: float | None = None


# Magnitude slang the $-regex cannot normalize — forces the analyzer path.
_MAGNITUDE_RE = re.compile(
    r"\d\s*(?:k|m)\b|\d[\d.,]*\s*(?:million|thousand|billion|nghìn|nghin|triệu|trieu|tỷ|ty|củ)",
    re.IGNORECASE,
)


def _needs_analyzer(query: str, regex_budget: float | None) -> bool:
    """Run the LLM analyzer when the regex has no answer or can't be trusted."""
    return regex_budget is None or _MAGNITUDE_RE.search(query) is not None


async def _analyze_query(model: Any, query: str) -> QueryFilters:
    """Temp-0 JSON extraction of {category, max_price}. Raises on failure (caller fails open)."""
    agent = Agent(model, output_type=QueryFilters, system_prompt=ANALYZER_PROMPT, name="query_analyzer")
    res = await agent.run(query, model_settings={"temperature": 0})
    return res.output


async def _match_category(hint: str) -> str | None:
    """Return the stored category spelling on case-insensitive match, else None."""
    async with async_session_factory() as db:
        rows = (await db.execute(select(Product.category).where(Product.is_active.is_(True)).distinct())).all()
    for (c,) in rows:
        if c and c.lower() == hint.lower():
            return c
    return None


async def _resolve_shopping_filters(
    model: Any, query: str, regex_budget: float | None, prefetch: QueryFilters | None = None
) -> tuple[str | None, float | None, str]:
    """Resolve (category_filter, max_price, search_text), failing open to regex."""
    if prefetch is not None:
        category = await _match_category(prefetch.category) if prefetch.category else None
        search_text = f"{query} {prefetch.category}" if prefetch.category and category is None else query
        return category, prefetch.max_price if prefetch.max_price is not None else regex_budget, search_text
    hint: str | None = None
    max_price = regex_budget
    if _needs_analyzer(query, regex_budget):
        try:
            analyzed = await asyncio.wait_for(_analyze_query(model, query), timeout=20.0)
            hint = analyzed.category
            if analyzed.max_price is not None:
                max_price = analyzed.max_price
        except Exception:
            logger.warning("query analyzer failed, falling back to regex", exc_info=True)
    category = await _match_category(hint) if hint else None
    search_text = f"{query} {hint}" if hint and category is None else query
    return category, max_price, search_text


async def _route_intent(model: Any, query: str, deps: Deps) -> str:
    """Analyzer-routed: one temp-0 call returns intent + shopping filters together.

    No keyword lists — the analyzer reads meaning, and its filters are reused
    for shopping via deps.analysis (no second analyzer call downstream).
    """
    try:
        deps.analysis = await asyncio.wait_for(_analyze_query(model, query.strip()), timeout=20.0)
        if deps.analysis.intent in ("shopping", "docs", "general"):
            return deps.analysis.intent
    except Exception:
        logger.warning("intent analyzer failed, defaulting to docs", exc_info=True)
    return "docs"


def _catalog(docs: list[dict]) -> str:
    if not docs:
        return "No documents in the library yet."
    return "Available documents in the library:\n" + "\n".join(
        f"- {d.get('clean_title') or d.get('title') or 'Document'}"
        + (f" (Ref: {d.get('reference')})" if d.get("reference") else "")
        + f" — {d.get('chunks', 0)} chunks"
        for d in docs
    )


async def _inject_catalog() -> str:
    """Doc-library catalog, docs agent only (shopping/general never see it)."""
    try:
        docs = await asyncio.wait_for(asyncio.to_thread(get_retrieval().list_documents), timeout=3.0)
    except Exception:
        logger.warning("Catalog fetch timed out, using fallback", exc_info=True)
        return "Available documents in the library: (catalog temporarily unavailable)"
    logger.info("Catalog injected n=%d", len(docs))
    return _catalog(docs)
