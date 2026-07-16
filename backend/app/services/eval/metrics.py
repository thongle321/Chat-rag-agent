"""Evaluation scoring functions for RAG answers."""

from __future__ import annotations

from app.services.eval.judge import (
    ANSWER_RELEVANCE_SYSTEM_PROMPT,
    CONTEXT_PRECISION_SYSTEM_PROMPT,
    CONTEXT_RECALL_SYSTEM_PROMPT,
    FAITHFULNESS_SYSTEM_PROMPT,
    OllamaJudge,
)
from app.services.eval.models import EvalResult
from app.services.rag import _format_context


def _truncate(text: str, limit: int = 3000) -> str:
    return text[:limit] if text else ""


def evaluate_answer(
    query: str,
    answer: str,
    context_docs: list,
    judge: OllamaJudge,
) -> EvalResult:
    """Score a single query/answer pair against retrieved documents.

    4 judge calls using system+human prompts. Overall = equal weight average.
    """
    if not answer or answer.startswith("Sorry,"):
        return EvalResult(error="empty/error answer")

    context = _format_context(context_docs) if context_docs else "No context retrieved."
    context_truncated = _truncate(context)

    # Context Precision: score first 3 chunks
    chunk_scores = []
    for doc in context_docs[:3]:
        chunk_text = _truncate(doc.page_content[:1000] if hasattr(doc, "page_content") else str(doc)[:1000])
        if chunk_text:
            chunk_scores.append(judge.score(CONTEXT_PRECISION_SYSTEM_PROMPT, f"Query: {query}\nContext chunk: {chunk_text}"))
    context_precision = sum(chunk_scores) / len(chunk_scores) if chunk_scores else 0.0

    # Faithfulness
    faithfulness = judge.score(
        FAITHFULNESS_SYSTEM_PROMPT,
        f"Query: {query}\nContext: {context_truncated}\nAnswer: {_truncate(answer, 1000)}",
    )

    # Answer Relevance
    answer_relevance = judge.score(
        ANSWER_RELEVANCE_SYSTEM_PROMPT,
        f"Query: {query}\nAnswer: {_truncate(answer, 1000)}",
    )

    # Context Recall
    context_recall = judge.score(
        CONTEXT_RECALL_SYSTEM_PROMPT,
        f"Query: {query}\nContext: {context_truncated}",
    )

    overall = (faithfulness + answer_relevance + context_precision + context_recall) / 4

    return EvalResult(
        faithfulness=faithfulness,
        answer_relevance=answer_relevance,
        context_precision=context_precision,
        context_recall=context_recall,
        overall=overall,
    )
