import re
from dataclasses import dataclass

from pydantic_ai import Agent
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class OllamaJudge(Evaluator[str, str]):
    rubric: str

    async def evaluate(self, ctx: EvaluatorContext[str, str]) -> float:
        try:
            model = OllamaModel(
                settings.ollama_model,
                provider=OllamaProvider(
                    base_url=settings.ollama_base_url,
                    api_key=settings.ollama_api_key or None,
                ),
            )
            system = (
                "You are an evaluator for a RAG chatbot. "
                f"Rubric: {self.rubric}\n"
                "Score from 0.0 to 1.0. Return ONLY a number."
            )
            agent = Agent(model, system_prompt=system)
            prompt = f"Question: {ctx.input}\n\nAnswer: {ctx.output}"
            if ctx.expected_output:
                prompt += f"\n\nExpected elements: {ctx.expected_output}"
            result = await agent.run(prompt)
            match = re.search(r'(\d+\.?\d*)', result.output.strip())
            if match:
                return max(0.0, min(1.0, float(match.group(1))))
        except Exception:
            logger.exception("OllamaJudge evaluation failed for case: %s", ctx.input)
        return 0.0
