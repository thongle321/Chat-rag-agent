"""Data models for RAG evaluation results."""

from __future__ import annotations


class EvalResult:
    __slots__ = ("faithfulness", "answer_relevance", "context_precision", "context_recall", "overall", "error")

    def __init__(
        self,
        faithfulness: float = 0.0,
        answer_relevance: float = 0.0,
        context_precision: float = 0.0,
        context_recall: float = 0.0,
        overall: float = 0.0,
        error: str | None = None,
    ):
        self.faithfulness = faithfulness
        self.answer_relevance = answer_relevance
        self.context_precision = context_precision
        self.context_recall = context_recall
        self.overall = overall
        self.error = error

    def to_dict(self) -> dict:
        return {
            "faithfulness": round(self.faithfulness, 4),
            "answer_relevance": round(self.answer_relevance, 4),
            "context_precision": round(self.context_precision, 4),
            "context_recall": round(self.context_recall, 4),
            "overall": round(self.overall, 4),
            "error": self.error,
        }
