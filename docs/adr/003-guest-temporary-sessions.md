# ADR 003 — Guest sessions are temporary (ChatGPT-like)

- **Status:** accepted (grilling session, 2026-09-04)
- **Date:** 2026-09-04

## Problem

Guest chats pushed temp `/c/:id` URLs; reload rehydrated them through the public
`GET /chat/sessions/:id` (anon rows are server-persisted and publicly readable).
Temporary in name only.

## Decision

1. Guest sessions live at `/uc/:id` (new route, `temporary` ChatView mode): mount checks
   local memory only, never the server — reload/direct visit → `replace('/')`.
   Account sessions stay at `/c/:id` with server fallback.
2. Guest tabs fire a `pagehide` beacon `DELETE`; backend allows deleting
   owner-less (`user_id NULL`) rows to anyone holding the UUID (no login).
3. Claim removed: PATCH/`_ensure_session` no longer absorb pre-login rows.
4. `GET /chat/sessions/:id` stays public; logged-in flows untouched.

## Consequences

- Reload / direct-URL visit on a temp id always lands on a blank composer.
- Lost-race beacons (crash, killed tab) leave invisible orphan rows.
- Guest history never follows a login.
