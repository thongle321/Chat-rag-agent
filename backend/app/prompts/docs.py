"""Docs prompt — the default base prompt plus the document catalog."""


def build_docs_prompt(base: str, catalog: str) -> str:
    """Docs = default base behavior + catalog data. No shopping rules here —
    those live in app/prompts/shopping.py for the shopping agent."""
    return base + "\n\n" + catalog
