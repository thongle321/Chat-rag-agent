# Citation Persistence Research — chat-rag-agent

Date: 2026-08-22
Scope: How to keep RAG source citations across browser refresh without a new DB table/column, grounded in THIS repo's stack.

## 0) Ground truth: why citations vanish today

* **DB shape** is fixed: `CREATE TABLE IF NOT EXISTS conversations (session_id TEXT PRIMARY KEY, messages TEXT NOT NULL)` — `backend/app/db/conversation_store.py:23-25`. No sources column exists by design.
* **Read/write** is `ModelMessagesTypeAdapter.validate_json(row[0])` / `dump_json(messages)` on the `messages TEXT` blob — `conversation_store.py:41` and `conversation_store.py:47`. The blob is `list[ModelMessage]` (`ModelRequest|ModelResponse`).
* **RAG citation flow** is ephemeral by construction: `Deps.retrieved: list[dict]` accumulates in `RAGState` (`app/services/rag.py:27-34`, `RAGState:37-44`), `_track_sources()` dedupes to `{n, title, reference, pages}` (`rag.py:113-134`), `search_documents` returns formatted context (`rag.py:137-156`), `stream_answer` yields `{"type":"sources", "sources": state.sources}` after filtering to actually-cited ids via `re.findall(r"\[(\d+)\]", ...)` (`rag.py:295-298`), and `POST /api/chat/query/stream` formats it as `event: sources\ndata: {"sources": [...]}` (`app/api/chat.py:64-65`).
* **Reload path strips sources**: `GET /chat/sessions/{id} -> SessionDetail` (`app/api/sessions.py:14-23`) calls `get_messages()` which maps every `ModelRequest/UserPromptPart` and `ModelResponse/TextPart` to `{role, content}` only (`app/services/rag.py:69-80`, `app/models/schemas.py:34-37`). `SessionDetail.messages: list[SessionMessage]` (`schemas.py:39-40`) has no `sources` field.
* **Frontend mirrors ephemerality**: `streamMsg.sources` is set only via `onSources` from `event:sources` (`frontend/src/stores/chat.ts:197`, `frontend/src/api/index.ts:79-80`), rendered in `UAccordion Sources` + `withCitationLinks` that rewrites `[1]` -> `#cite-1` (`frontend/src/pages/index.vue:37-39`, `index.vue:142-166`). `fetchSessionMessages` rebuilds `conv.messages` as `{id, role, text}` with no `sources` (`chat.ts:98-107`). Refresh -> sources gone. `localStorage` only stores `{id, title, pinned, createdAt, sessionId}` (`chat.ts:63-72`), no message bodies.

> Consequence is intentional: user refused new `sources` column, got ephemeral citations. Question now: can RAG itself persist them without schema change?

---

## 1) What "no new table/column" allows

* SQLite **can** add a column (`ALTER TABLE ... ADD COLUMN ...` is supported with restrictions: no PK/UNIQUE, no `CURRENT_TIMESTAMP` default, constant default if NOT NULL) — `https://www.sqlite.org/lang_altertable.html` §4. But this report honors the constraint: **no new column/table**.
* The only mutable durable field is the existing `messages TEXT` blob. Anything persisted must live **inside** that JSON, or be reconstructible externally without new server state.

### What pydantic_ai guarantees persists inside that blob

* `ModelMessagesTypeAdapter = TypeAdapter(list[ModelMessage])` (`backend/.venv/Lib/site-packages/pydantic_ai/messages.py:2768`) is the documented persist/load boundary — `https://ai.pydantic.dev/core-concepts/message-history/#storing-and-loading-messages-to-json`.
* **What survives a round-trip**: `ModelMessagesTypeAdapter` preserves **every field, including application-only `metadata`** that is *not sent to the LLM*. Quote: "`ModelMessagesTypeAdapter` preserves every field, including application-only annotations such as `TextContent.metadata` that are *not sent to the model*." — same doc. JSON round-trip normalizes tuples/datetimes; `dump_python -> validate_python` is lossless.
* `ModelRequest.metadata: dict[str, Any] | None` and `ModelResponse.metadata: dict[str, Any] | None` — both documented `Additional data that can be accessed programmatically by the application but is not sent to the LLM.` — `messages.py:1861` and `messages.py:2602`. `TextContent.metadata: Any = None` — `messages.py:526` (same contract).
* Contrast: **UI adapters** (Vercel AI, AG-UI) intentionally drop app-only fields when round-tripping through their wire format — documented as by-design — `https://ai.pydantic.dev/core-concepts/message-history/#storing-and-loading-messages-to-json` "The UI adapters are different...". Not relevant here because repo persists via `ModelMessagesTypeAdapter` directly, not via a UI adapter.

### What Chroma guarantees

* `collection.get(ids=[...], include=["documents","metadatas"])` retrieves by exact id without ranking — `https://docs.trychroma.com/docs/querying-collections/query-and-get` §Get. Repo already uses `collection.get(ids=[...])` to fuse RRF results (`app/db/vector_store.py:161`) and `collection.get(where={"title": title})` for deletes (`vector_store.py:208`).
* Metadata filtering (`where`) — `https://docs.trychroma.com/docs/querying-collections/metadata-filtering`. Metadata shape at ingest is `{title, clean_title, reference, type, chunk/page}` (`vector_store.py:178-200`, `document_ingest.py` via `base_metadata`).
* Hybrid query recomputes every time (`vector_store.py:143-172`): `bm25s.tokenize` + dense `query` + `rrf(k=60)` — no stored citation snapshot.

### What the browser guarantees

* `localStorage` and `sessionStorage` per WHATWG Storage Standard — `https://html.spec.whatwg.org/multipage/webstorage.html` §12.2, `https://storage.spec.whatwg.org/` (quota table). `localStorage` persists across reloads/close per origin; `sessionStorage` per tab survives reload but dies on tab close. MDN confirms ≥5 MiB per origin quota, `QuotaExceededError` — `https://developer.mozilla.org/en-US/docs/Web/API/Web_Storage_API` and `https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria`.

### What Vercel/RAG canon does

* Vercel RAG pattern: **each message carries its own sources**; `[id]` tags in the answer resolve against `source-url` / `source` parts on the same message; sources stream *before* first token as discrete parts — `https://vercel.com/kb/guide/building-ai-chat-app-with-rag-and-citations-on-vercel` and `https://vercel.com/kb/guide/rag-chatbot-production-architecture-on-vercel` ("Citations the reader can check... those sources stream to the client with the message that cites them", "Each message carries its own sources"). The AI SDK equivalent is `messageMetadata` / `sources` attached to `UIMessage` persisted as JSONB (`rag-chatbot` example uses `messageMetadata: () => ({sources})`) — `https://ai-sdk.dev/cookbook/guides/rag-chatbot`.

---

## 2) Options evaluated against THIS repo

### (a) Ephemeral only — current, no persistence

* **How**: Keep `event:sources` transient; `GET /sessions/{id}` stays `{role, content}`-only.
* **Pros**: Zero change. No LLM contamination.
* **Cons**: Refresh = citations lost. Breaks audit/provenance contract. User already hit this.
* **Primary source**: `rag.py:294-298` (sources yielded but never saved), `sessions.py:22` (maps without sources).
* **Verdict**: Baseline to beat.

### (b) Embed source-pointer inside existing `messages TEXT` blob — NO schema change

Two sub-variants, both reuse the single `messages` column:

**b1) HTML comment in answer text** `<!-- sources: ["id1","id2"] -->` appended to `TextPart.content` before `save_messages`.

* Persists because `TextPart.content: str` is inside the serialized blob (`messages.py` TextPart definition, `conversation_store.py:47`).
* No `ALTER TABLE` — blob mutation only.
* **Must strip before replay** or LLM sees the comment. Patch `get_messages()` or `_keep_recent()` (`rag.py:86-91`) to strip `<!--.*?-->` on load, or better store pointer out-of-band.
* Fragile: string munging, quote/escape bugs, grows `text` field.

**b2) Message metadata sidecar — preferred** `ModelResponse.metadata = {"sources": [ids] or [{n,title,ref}]}`

* Persists because `ModelResponse.metadata` is preserved by `ModelMessagesTypeAdapter` (`messages.py:2602`) and documented as `What survives a round-trip` (`message-history.md`). Not sent to LLM — so no prompt pollution.
* No `ALTER TABLE`, no text munging. Minimal diff: set metadata before `save_messages`, read it in `get_messages` / `SessionDetail` projection.
* JSON-typing caveat: `Any` means round-trip normalizes (tuple->list, datetime->ISO) — doc warns. Use JSON-safe scalars (str/int/list/dict) for ids.
* **This is the RAG-native answer** to "RAG itself offers a way?" — yes: `ModelMessage.metadata` is the framework-provided sidecar for exactly this.

*Both b1/b2 satisfy "ids live inside the blob" as the task describes.*

### (c) Lazy re-derive on reload — re-run `hybrid_query(question, embedding, k=8)` per turn

* **How**: On `GET /sessions/{id}`, re-embed last user question and call `vector_store.hybrid_query` again (`rag.py:150` pattern) to recompute sources.
* **Pros**: No storage at all.
* **Cons**: **Non-deterministic, index-drift**. `rrf(k=60)` (`vector_store.py:53`), `k*2` candidates + `bm25s.tokenize(stopwords=_STOPWORDS)` (`vector_store.py:98,152-154`) mean results shift as documents are added/deleted, BM25 index rebuilds (`vector_store.py:83-108`), or query prefix changes (`rag.py:148`). No guarantee the re-derived ids match the model's original citations; answer may cite `[2]` that now maps to a different doc — broken provenance. Also costs embedding + retrieval on every reload.
* **Primary source**: `vector_store.py:143-172` hybrid determinism limits; `rag.py:113` doc "RRF scores aren't cosine similarity".
* **Verdict**: Unsound for citations. Reject except as fallback diagnostic.

### (d) Hydrate at render time — fetch full metadata from vector DB by ids

* **How**: Persist **only ids** (via b2 sidecar or b1 comment). At display time, call `collection.get(ids=[...])` to fetch authoritative `{clean_title, reference, pages}` from Chroma — the "full citation authority remains vector DB" pattern the task names.
* **Pros**: Single source of truth for titles/refs (no stale copy). If a title is corrected in Chroma, citations show corrected value. `collection.get(ids=[...])` is documented and exists in repo (`vector_store.py:161`).
* **Cons**: Requires network to Chroma; deleted doc -> `get` returns empty (handle gracefully). Adds one `get` per message on reload (batch ids across messages to amortize).
* **Primary sources**: `https://docs.trychroma.com/docs/querying-collections/query-and-get` (get by ids), `vector_store.py:161-163` (existing pattern), Vercel "Each message carries its own sources... rendering is a lookup" (`vercel.com/kb/guide/building-ai-chat-app-with-rag-and-citations-on-vercel`).
* **Verdict**: Complement to (b), not standalone — use with (b2) ids pointer.

### (e) Frontend `localStorage` mirror of `event:sources` keyed by `sessionId:turn`

* **How**: `onSources` writes `localStorage.setItem("sources:"+sessionId+":"+turnId, JSON.stringify(sources))`; `fetchSessionMessages` hydrates from it.
* **Pros**: Zero backend change. Survives refresh per MDN/WHATWG (`localStorage` persists across sessions) — `https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage`, `https://html.spec.whatwg.org/multipage/webstorage.html`.
* **Cons**: **Device/tab-local only** — not durable, not cross-device, not shareable via URL, cleared on "Clear site data", incognito, or manual `localStorage.clear()`. Quota 5 MiB (`https://storage.spec.whatwg.org/` table, `https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria`). Silent divergence between clients; no server-side audit. `sessionStorage` variant dies on tab close.
* **Verdict**: Useful as optimistic UI cache, not provenance.

### (f) Other RAG-native patterns found in primary docs

* **Vercel `messageMetadata` / `source-url` parts** — sources as typed parts on `UIMessage` persisted as JSONB (`rag-forge` stores `UIMessage[]` JSONB; `ai-sdk.dev/cookbook/guides/rag-chatbot` uses `createUIMessageStreamResponse({ messageMetadata: () => ({sources}) })`). Equivalent in this stack is `ModelResponse.metadata` (server) + hydrate on GET — same idea, typed not string-embedded.
* **Tool-output part** — serialize citations as a `ToolReturnPart` after `search_documents`. Pydantic AI repairs history but would surface this as tool traffic to the model; noisier than metadata sidecar. Not needed.
* **`TextContent.metadata`** — per-item user content metadata, also preserved by adapter (`messages.py:526`) but scoped to user parts, not assistant citations. Less direct than `ModelResponse.metadata`.

---

## 3) Comparison (repo-grounded)

| Option | Persists across refresh? | Needs schema change? | LLM sees it? | Authority for title/ref | Cross-device? | Cost |
|---|---|---|---|---|---:|---|
| (a) ephemeral | no | no | no | — | — | 0 |
| (b1) HTML comment in text | yes (inside blob) | no | yes unless stripped | captured or Chroma | yes | tiny |
| **(b2) `ModelResponse.metadata` sidecar** | **yes (inside blob)** | **no** | **no** | captured or Chroma | **yes** | tiny |
| (c) re-derive | approx, drift | no | no | live index | yes | embedding+RRF each load |
| (d) hydrate by id | yes if paired with (b) | no | no | Chroma live | yes | 1× `get(ids)` |
| (e) localStorage | per-device only | no | no | captured | no | 5 MiB cap |
| Vercel `messageMetadata` | yes (JSONB) | yes (in their stack) | no | captured | yes | similar to (b2) |

---

## 4) Recommended default — ponytail minimal

**Use (b2) + (d) together**:

1. **Persist only ids** in `ModelResponse.metadata` inside the existing `messages TEXT` blob. In `stream_answer` (`app/services/rag.py:294-298`), right before `save_messages`, attach `state.new_messages[-1].metadata = {"sources": [s for s in state.sources]}` or `{"source_ids": [doc_id ...]}`. Because `ModelMessagesTypeAdapter.dump_json` includes `metadata` (`messages.py:2602`), the blob now carries the pointer without any `ALTER TABLE`.
2. **Hydrate on read** by `collection.get(ids=...)` (batch across turn) to fetch `clean_title/reference/pages` live — `vector_store.py:161` pattern, `https://docs.trychroma.com/docs/querying-collections/query-and-get`. If a doc was deleted, render `[deleted]` rather than lie.

Pseudo-diff (2 files, ~10 lines):

```python
# rag.py stream_answer, after cited filter
state.sources = [s for s in deps.retrieved if s["n"] in cited]
# ponytail: ids pointer lives inside existing blob, no new column
state.new_messages[-1].metadata = {"sources": state.sources}  # or {"source_ids": [d["id"]...]}
await save_messages(sid, history + state.new_messages)

# get_messages: expose it
# if isinstance(m, ModelResponse) and m.metadata and "sources" in m.metadata:
#   result.append({"role":"assistant","content":part.content,"sources":m.metadata["sources"]})
```

Frontend `fetchSessionMessages` (`stores/chat.ts:98-107`) then receives `sources` and renders `UAccordion` without change; iterative `collection.get(ids)` can also be done backend to return fresh titles.

**Why this is RAG-native**: `ModelMessage.metadata` exists precisely as a "user-space container for arbitrary application-specific data that is not sent to the LLM" (PR #3422, `https://github.com/pydantic/pydantic-ai/pull/3422`, issue `https://github.com/pydantic/pydantic-ai/issues/3404`) and `What survives a round-trip` (`https://ai.pydantic.dev/core-concepts/message-history/#storing-and-loading-messages-to-json`). Vercel's canon that "each message carries its own sources" (`https://vercel.com/kb/guide/building-ai-chat-app-with-rag-and-citations-on-vercel`) maps to `metadata` here. Chroma remains citation authority via `get(ids=)` (`https://docs.trychroma.com/docs/querying-collections/query-and-get`).

**Fallback if `metadata` unavailable** (repo pins `pydantic-ai>=2.19` — check `pyproject.toml:14`): use (b1) HTML comment `<!-- cit:["id",...] -->` and strip on load. Same blob trick, more fragile.

**Optional accelerator**: mirror `event:sources` to `localStorage` (`e`) for instant paint before server hydrate — keyed `${sessionId}:${msgId}`. Treat as cache only; server blob is truth.

### Ceiling

* Metadata pointer **duplicates ids per turn** — blob grows O(turns * sources) but ids are tiny vs. text; bound by `_MAX_STORED_MESSAGES=20` (`conversation_store.py:11`) and `_MAX_HISTORY=10` (`rag.py:83`), so cap is ~20*8 ids.
* Hydration adds **one `get(ids)` per reload**; batch all ids into single call. If Chroma is down or doc deleted, citations degrade gracefully — no longer authoritative, but no crash.
* If provenance must survive **doc edits** exactly as cited at answer time (frozen title/ref), store full `{title, reference, pages}` in metadata instead of ids — trades staleness for fidelity. Choose per compliance need.
* When transcript volume justifies it, graduate to a proper `sources` JSONB side table or per-message row — until then this sidecar is minimal and correct.

---

## 5) Verification

* `ruff check app/services/rag.py app/api/sessions.py app/db/conversation_store.py`
* `python -c "from pydantic_ai.messages import ModelResponse; r=ModelResponse(...); ..."` — round-trip `ModelMessagesTypeAdapter.dump_json/validate_json` preserves `metadata`.
* Manual: send prompt requiring citations -> refresh -> `GET /chat/sessions/{id}` returns messages with `sources`; `Network > query/stream` shows `event: sources`; reload shows same citations without re-running `hybrid_query`; `documents` delete still renders fallback.

---

## Sources — primary only

* Repo: `backend/app/db/conversation_store.py:23-25`, `conversation_store.py:41`, `conversation_store.py:47`, `app/services/rag.py:27-44`, `rag.py:69-80`, `rag.py:83`, `rag.py:86-91`, `rag.py:113-134`, `rag.py:137-156`, `rag.py:294-298`, `app/api/chat.py:64-65`, `app/api/sessions.py:14-23`, `app/models/schemas.py:34-40`, `app/db/vector_store.py:53`, `vector_store.py:83-108`, `vector_store.py:143-172`, `vector_store.py:161`, `vector_store.py:178-200`, `frontend/src/stores/chat.ts:63-72`, `chat.ts:98-107`, `chat.ts:183-197`, `frontend/src/pages/index.vue:37-39`, `index.vue:142-166`, `frontend/src/api/index.ts:79-80`, `backend/pyproject.toml:14`, `backend/.venv/Lib/site-packages/pydantic_ai/messages.py:526`, `messages.py:1861`, `messages.py:2602`, `messages.py:2768`
* Docs: `https://ai.pydantic.dev/core-concepts/message-history/#storing-and-loading-messages-to-json`, `https://www.sqlite.org/lang_altertable.html` §4, `https://docs.trychroma.com/docs/querying-collections/query-and-get` (Get), `https://docs.trychroma.com/docs/querying-collections/metadata-filtering`, `https://html.spec.whatwg.org/multipage/webstorage.html` §12.2, `https://storage.spec.whatwg.org/` (quota table), `https://developer.mozilla.org/en-US/docs/Web/API/Web_Storage_API`, `https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria`, `https://vercel.com/kb/guide/building-ai-chat-app-with-rag-and-citations-on-vercel`, `https://vercel.com/kb/guide/rag-chatbot-production-architecture-on-vercel`, `https://ai-sdk.dev/cookbook/guides/rag-chatbot`, `https://github.com/pydantic/pydantic-ai/pull/3422`, `https://github.com/pydantic/pydantic-ai/issues/3404`
