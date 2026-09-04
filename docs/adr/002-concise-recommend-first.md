# ADR 002 — Conciseness fix: recommend-first product flow

- **Status:** accepted (grill-with-docs Round 1–2, 2026-09-04)
- **Source:** `docs/research/ecommerce-rag-lessons.md` (reference: `ThanhLa1802/rag_chatbot_ecommerce`)

## Decision

1. **Recommend-first RULE 10** — always call `search_products`, even when vague;
   answers ≤5 lines; at most ONE question, only on empty results.
2. **Hard price pre-gate** — parsed `max_price` becomes SQL `price <= budget`
   before embedding/top-k (fail-open: no budget → no filter). Replaces the soft
   `_rerank` price nudge as the primary price mechanism.
3. **LLM query analyzer** — temp-0 JSON `{category, max_price}` per shopping tool
   call (fail-open to regex); regex stays as fallback. Handles "500k / 2 million"
   slang the `$`-regex cannot.
4. **Pre-search chip branch deleted** — post-empty `followups` stay as the single
   question path.
5. **RULE 12 conditional** — why-pick clause stays required; comparison table +
   honest caveat only on compare-intent ("compare", "vs", "which is better") or 3+ cites.
6. **Analyzer category** — exact DB match → hard filter; non-match → appended to
   the search text (feeds cosine + token-overlap boost). Never fails closed.

## Consequences

- One extra mini-model call per shopping invocation (accepted cost).
- Reverses ADR 001's pre-search clarifier decision (D6) — recorded here, not edited there.
