# ADR 001 — Shopping replication: no-schema slice

- **Status:** accepted (Round 1, grill-with-docs)
- **Date:** 2026-09-04

## Decision

Implement the ChatGPT-shopping replication as a no-schema slice:
prompt + deterministic re-rank + read-time hydration. No DB migration,
no ratings columns, no scheduler, outbound Buy link only.

## Context

`docs/research/chatgpt-shopping-replication.md` lists 8 features. Full slice needs
`star_rating`/`review_count`/`brand`/`sale_price` columns + daily sync. Catalog source
of truth is manual + CSV; single-merchant offline by design (no ACP checkout —
approved-partners-only upstream).

## Consequences

- Ratings-dependent ranking boost and card slots stay OUT until a later ADR.
- Re-rank uses only existing columns: `stock`, `price`, `category`.
- Import validation (reject imageless/priceless) possible without schema — D8 open.
