"""RAG evaluation service — LLM-as-judge scoring for answer quality.

Internal dev tool only. Not exposed to users.
Prompts from github.com/vikrambhat2/rag-evaluator (MIT-licensed).
"""

from app.services.eval.judge import OllamaJudge
from app.services.eval.metrics import evaluate_answer
from app.services.eval.models import EvalResult

__all__ = ["EvalResult", "OllamaJudge", "evaluate_answer"]
