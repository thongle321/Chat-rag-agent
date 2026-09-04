# CONTEXT.md — chat-rag-agent (grill-with-docs paper trail)

## Shopping replication (docs/research/chatgpt-shopping-replication.md) — settled

- **D1 Scope:** No-schema wins — prompt + re-rank + hydration only, no DB migration.
  Consequence: ratings (`star_rating`/`review_count`), `brand`, `sale_price` columns are OUT.
- **D3 Catalog:** Manual + CSV import as today, no scheduler. No nightly Shopify sync.
- **D4 Buy CTA:** Outbound PDP link. No in-chat cart, no ACP checkout.

## Glossary (domain-modeling)

- **Catalog:** offline `products` table (admin-imported). Not web search.
- **Strict grounding:** agent may cite only `[Pn]` SKUs returned by `search_products`.
- **GATE:** `PRODUCT_SCORE_GATE=0.30` in `products.py`, applied pre-slice.
- **Followups:** `followups` SSE event; today emitted only when `products_searched and nothing cited`.
- **Hydration:** read-time price/stock from DB at stream time (like doc citation hydration).

## Open (frontier) — all settled 2026-09-04

- D5 re-rank: all three boosts (in-stock + price-constraint + category) after GATE, before top-k.
- D6 clarifiers: pre-search chips on vague queries; post-empty followups stay as fallback.
- D7 prompt: REQUIRE why-pick + comparison table (≥2 cited) + honest caveat in SHOPPING RULES.
- D8 hygiene: CSV rejects imageless/priceless rows with skipped count.

## Conciseness fix (ADR 002, grill-with-docs Round 1–2, reverses D6/D7 scope)

- Recommend-first RULE 10: always call search_products; ≤5 lines; ≤1 question, empty-only.
- Hard price pre-gate (SQL `price <= budget`, fail-open); analyzer {category, max_price}.
- Pre-search chip branch deleted; post-empty chips are the single question path.
- RULE 12: why-pick required; table + caveat only on compare-intent or 3+ cites.
- Analyzer category: exact DB match → filter; else appended to search text.
