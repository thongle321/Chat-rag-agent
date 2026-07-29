import warnings

import pytest
from pydantic_evals import Dataset
from pydantic_evals.evaluators import IsInstance

from app.services.rag import answer_question, get_graph

from tests.eval_dataset import cases
from tests.evaluators import OllamaJudge


async def eval_task(question: str) -> str:
    result = await answer_question(question)
    return result.answer


@pytest.mark.asyncio
async def test_rag_evaluation():
    dataset = Dataset[str, str, None](
        name="rag_eval",
        cases=cases,
        evaluators=[
            IsInstance(type_name="str"),
            OllamaJudge(
                rubric=(
                    "The answer correctly addresses the question "
                    "using only information from the retrieved context. "
                    "It should be accurate and include relevant details."
                )
            ),
        ],
    )
    report = await dataset.evaluate(eval_task, max_concurrency=1, progress=False)

    for case in report.cases:
        warnings.warn(
            f"Case '{case.name}': "
            f"scores={ {k: f'{v:.2f}' for k, v in case.scores.items()} }, "
            f"pass={all(a.value for a in case.assertions.values())}",
            stacklevel=0,
        )

    avg = report.averages()
    assert avg is not None, "No results to evaluate"
    judge_score = avg.scores.get("OllamaJudge", 0.0)
    assert judge_score >= 0.5, f"Average OllamaJudge score {judge_score:.2f} below 0.5"
    assert report.failures == [], f"{len(report.failures)} task failures"
