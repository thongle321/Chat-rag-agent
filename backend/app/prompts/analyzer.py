"""Analyzer prompt — one temp-0 call returning intent + shopping filters."""

ANALYZER_PROMPT = (
    "Classify the user query and extract shopping filters as JSON. "
    "intent: 'shopping' (wants to buy/find/compare products, any goods or gear), "
    "'general' (greeting, small talk, questions about the assistant itself), "
    "else 'docs' (asks about the stored documents). "
    "category: the product category in the user's own words (or null). "
    "max_price: the price ceiling as a plain number (or null) — normalize magnitude "
    "slang (500k=500000, 2 million=2000000). No ceiling mentioned means null."
)
