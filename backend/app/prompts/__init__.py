"""Task prompts — one self-contained system prompt per agent.

shopping/general own their full prompt. docs builds on the default base prompt
(Settings.context_prompt) plus the catalog. Adding a task = new file + one
branch in get_prompt.
"""

from app.prompts.analyzer import ANALYZER_PROMPT
from app.prompts.docs import build_docs_prompt
from app.prompts.general import GENERAL_PROMPT
from app.prompts.shopping import SHOPPING_PROMPT

__all__ = ["ANALYZER_PROMPT", "GENERAL_PROMPT", "SHOPPING_PROMPT", "build_docs_prompt", "get_prompt"]


def get_prompt(task: str, base: str = "", catalog: str = "") -> str:
    """Return the full system prompt for a task agent."""
    if task == "shopping":
        return SHOPPING_PROMPT
    if task == "general":
        return GENERAL_PROMPT
    return build_docs_prompt(base, catalog)
