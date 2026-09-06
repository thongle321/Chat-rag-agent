"""Answer facade — re-exports the split modules so existing importers don't change.

Split (candidate 1): routing (intent + filters + shared types) lives in
rag_routing, thin retrieval tools in rag_tools, assembly + streaming in
rag_runner. Import from those modules directly in new code.
"""

from app.services.rag_routing import Deps, QueryFilters
from app.services.rag_runner import (
    RAGState,
    ShoppingAnswer,
    answer_question,
    close,
    get_messages,
    stream_answer,
)
from app.services.rag_tools import search_documents, search_products, search_shopify_catalog

__all__ = [
    "Deps",
    "QueryFilters",
    "RAGState",
    "ShoppingAnswer",
    "answer_question",
    "close",
    "get_messages",
    "search_documents",
    "search_products",
    "search_shopify_catalog",
    "stream_answer",
]
