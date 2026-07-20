"""Ollama LLM-as-Judge for RAG evaluation scoring."""

from __future__ import annotations

import json

from app.services.rag import _get_model
from app.utils.logger import get_logger

logger = get_logger(__name__)

FAITHFULNESS_SYSTEM_PROMPT = """You are an evaluation judge. Your task is to assess the faithfulness of an answer.
Faithfulness measures whether EVERY claim in the answer is supported by the provided context chunks.
A score of 1.0 means all claims are fully supported. A score of 0.0 means none are supported.
Evaluate carefully, then return ONLY a JSON object with a single key "score" containing a float between 0.0 and 1.0.
No explanation, no other text. Example: {"score": 0.85}"""

ANSWER_RELEVANCE_SYSTEM_PROMPT = """You are an evaluation judge. Your task is to assess the relevance of an answer to a question.
Answer relevance measures how well the answer addresses the specific question asked.
A score of 1.0 means the answer perfectly addresses the question. A score of 0.0 means the answer is completely off-topic.
Evaluate carefully, then return ONLY a JSON object with a single key "score" containing a float between 0.0 and 1.0.
No explanation, no other text. Example: {"score": 0.85}"""

CONTEXT_PRECISION_SYSTEM_PROMPT = """You are an evaluation judge. Your task is to assess context precision.
Context precision measures how many of the retrieved chunks are actually relevant to answering the query.
A score of 1.0 means all chunks are relevant. A score of 0.0 means none are relevant.
Evaluate carefully, then return ONLY a JSON object with a single key "score" containing a float between 0.0 and 1.0.
No explanation, no other text. Example: {"score": 0.85}"""

CONTEXT_RECALL_SYSTEM_PROMPT = """You are an evaluation judge. Your task is to assess context recall.
Context recall measures whether the retrieved chunks contain all the information needed to produce the ground truth answer.
A score of 1.0 means the chunks contain all necessary information. A score of 0.0 means they contain none.
Evaluate carefully, then return ONLY a JSON object with a single key "score" containing a float between 0.0 and 1.0.
No explanation, no other text. Example: {"score": 0.85}"""


class OllamaJudge:
    """LLM-as-Judge using ChatOllama for structured scoring."""

    def __init__(self):
        self.llm = _get_model()

    def score(self, system_prompt: str, user_prompt: str) -> float:
        """Send system+human prompt, return float 0.0–1.0. JSON parsing with fallback."""
        try:
            response = self.llm.invoke([("system", system_prompt), ("human", user_prompt)])
            content = response.content.strip()

            if "{" in content:
                start = content.find("{")
                end = content.rfind("}") + 1
                content = content[start:end]

            parsed = json.loads(content)
            raw_score = float(parsed["score"])
            return max(0.0, min(1.0, raw_score))

        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
            logger.warning("Failed to parse judge response: %s. Defaulting to 0.0", e)
            return 0.0
        except Exception as e:
            logger.warning("Judge invocation failed: %s. Defaulting to 0.0", e)
            return 0.0
