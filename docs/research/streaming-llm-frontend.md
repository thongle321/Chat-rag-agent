# Streaming LLM Response: Pydantic AI → FastAPI SSE → Nuxt UI Vue

Date: 2026-08-22
Repo: `chat-rag-agent`


## 1. Backend Streaming Contract (Pydantic AI)

### 1.1 Agent Streaming Primitive — Primary Source: `https://ai.pydantic.dev` (llms.txt index) + repo `backend/app/services/rag.py:223`, `backend/.venv/Lib/site-packages/pydantic_ai/result.py:617`

- **Pydantic AI official:** An `Agent` exposes `run_stream()` returning a `StreamedRunResult`. The result offers `stream_text(delta=True|False)` and `stream_output()`. Verified in repo docs index (`pydantic.dev/docs/ai/...`) and in installed package `pydantic_ai/result.py:617`:
  ```python
  async def stream_text(self, *, delta: bool = False) -> AsyncIterator[str]:
      # delta=False (default): yield the full accumulated text each iteration
      # delta=True: yield only the new chunk
  ```
- **Critical detail:** `delta=False` is the default and yields the *full accumulated text* each time. With `delta=False` and `handlers.onDelta(data.content)` doing `streamMsg.text += content` on the frontend, each chunk re-appends the full prefix → the doubling bug observed (`“Chào bạn…”` repeated with growing prefix). Fix is `stream_text(delta=True)` — repo fix at `backend/app/services/rag.py:253`.

- **Tool loop streaming:** When an agent has `tools=[search_documents, list_documents]`, `run_stream` internally performs the tool-call round(s) (non-streamed) then streams the final `TextPart`. `StreamedRunResult` docs confirm `run_stream` is an async context manager (`async with agent.run_stream(...) as result:`). Our earlier SSE streaming plumbing relied on this; `pydantic-ai 2.31.0` requires `async with` (repo fix verified).

### 1.2 FastAPI SSE Transport — Primary Source: `backend/app/api/chat.py:60`, `backend/app/services/rag.py:224-270`

- `POST /api/chat/query/stream` returns `StreamingResponse(event_stream(), media_type="text/event-stream")`.
- `stream_answer()` is the single streaming source — yields event dicts: `text_delta` → `data: {"content": chunk}\n\n`, `sources` → `event: sources\ndata: {"sources": [...]}\n\n`, `done` → `event: done\ndata: {"session_id": ..., "model": ...}\n\n`, `error` similarly. Verified in `chat.py:60-70` `event_stream()` formatting and in `rag.py:249-270` yields.

- **SSE spec requirement (primary: `text/event-stream` spec):** Each logical message is `event:` + `data:` + blank line (`\n\n`). Client parsers split on `\n` and dispatch per `event:`.

### 1.3 Backend Buffering Pitfall — Primary Source: `backend/app/main.py:82`, Starlette `GZipMiddleware`

- `app.add_middleware(GZipMiddleware, minimum_size=500)` buffers the entire `StreamingResponse` to gzip it, defeating `chunked` delivery. For `text/event-stream` the response must not be gzipped — otherwise the browser/Vite proxy receives a single gzipped body after the model finishes, so the frontend `USkeleton` stays visible then the full answer dumps at once. Fix pattern (primary source: Starlette `GZipMiddleware` docs + standard FastAPI SSE guidance): bypass GZip for `scope["path"] == "/api/chat/query/stream"` or any `content-type` containing `text/event-stream`, e.g. subclass `GZipMiddleware`.

---

## 2. Frontend SSE Consumption (Vue 3 + Nuxt UI v4 + Vite)

### 2.1 Fetch + ReadableStream — Primary Source: `frontend/src/api/index.ts:23`, `frontend/src/stores/chat.ts:164`, Vue 3 docs

- **Pattern:** `fetch(url, {method:"POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(...), signal})` → `response.body.getReader()` → `TextDecoder` → `buffer.split('\n')` → dispatch. This is the standard browser `fetch` streaming pattern for SSE without `EventSource` (needed for `POST` + `AbortSignal` for `Stop`).

- **Repo implementation (correct after fix):**
  ```ts
  // frontend/src/api/index.ts:45
  const reader = response.body.getReader();
  let buffer = '', currentEvent = 'message';
  while (true) {
    const {done, value} = await reader.read(); if (done) break;
    buffer += decoder.decode(value, {stream:true});
    const lines = buffer.split('\n'); buffer = lines.pop()||'';
    for (const raw of lines) {
      const line = raw.trimEnd();
      if (!line) { currentEvent='message'; continue; }
      if (line.startsWith('event: ')) { currentEvent=line.slice(7).trim(); continue; }
      if (!line.startsWith('data: ')) continue;
      const data = JSON.parse(line.slice(6)); // try/catch + console.error on bad JSON
      if (currentEvent==='sources') handlers.onSources?.(data.sources);
      else if (currentEvent==='error') handlers.onError(data.detail);
      else if (currentEvent==='done') handlers.onDone({session_id, model});
      else handlers.onDelta(data.content ?? ''); // also resets currentEvent after event types
    }
  }
  ```
- **Critical detail:** `JSON.parse(line.slice(6))` must be inside `try/catch` — a single malformed `\u` escape would kill the loop and leave `streamingText==''` → skeleton forever. Also reset `currentEvent='message'` after handling `sources`/`error`/`done` and on blank line, otherwise the next `data:` without an `event:` prefix would be misrouted.

- **Pinia + Vue reactivity — Primary Source: `frontend/src/stores/chat.ts:182-195`**
  ```ts
  const streamMsg: ChatMessage = {id:'streaming', role:'assistant', text:'', streaming:true};
  conv.messages.push(streamMsg);
  // onDelta: streamMsg.text += content  (mutates object already inside reactive ref array)
  // onDone:  streamMsg.streaming=false; streamMsg.id=Date.now()
  ```
  Vue 3 (`ref<Conversation[]>`) proxies nested objects on `push`, so direct `streamMsg.text +=` is reactive. This matches the recommended Nuxt UI Vue streaming pattern (see §3).

### 2.2 Markdown Incremental Rendering — Primary Source: `frontend/src/pages/index.vue:103`, `@comark/vue`, Nuxt UI

- **Nuxt UI v4** (`https://ui.nuxt.com/getting-started`) is a Vue UI library built on `Reka UI` + `Tailwind CSS` + `Tailwind Variants`; it provides 125+ accessible components (`UCard`, `UButton`, `UAvatar`, `USkeleton`, `UAlert`, etc.) but **has no built-in streaming/markdown component** — streaming text is rendered by the app’s own `Comark` (`@comark/vue`) component.
- **Pattern in `pages/index.vue:103-112`:**
  ```vue
  <template v-if="msg.streaming && !msg.text">
    <USkeleton .../> <!-- skeleton inside the same assistant bubble -->
  </template>
  <template v-else>
    <Suspense><Comark :markdown="msg.text" /></Suspense>
  </template>
  ```
  Modern ChatGPT/Muse style: **single assistant bubble** swaps skeleton → incremental `Comark` markdown token-by-token. The previous double-bubble (empty streaming bubble + separate `v-if="loading && !streamingText"` skeleton *below* the `v-for` loop) stacked two assistant-like bubbles during the tool round; the fix merges them inside one bubble.

- **Official guidance (Nuxt UI primary source `https://ui.nuxt.com/docs/getting-started`):** Nuxt UI components are SSR-compatible and work with `auto-imports` in Vue/Vite (as in `vite.config.ts:8` `ui({autoImport: {imports:['vue',...]}})`). No special streaming guard is needed beyond normal Vue reactivity; the incremental update comes from the Pinia `onDelta` mutation.

### 2.3 Vite Proxy — Primary Source: `frontend/vite.config.ts:27`

- Dev proxy `'/api' → 'http://localhost:8000'` must not buffer `text/event-stream`. Added `configure(proxyRes)` to force `cache-control: no-cache`, `connection: keep-alive`, `x-accel-buffering: no` for that content-type. Without it, Vite’s `http-proxy` can coalesce chunks (especially when upstream is gzipped — see §1.3), so `reader.read()` would yield one large `value` at the end, still rendered correctly after the parser fix but with no token-by-token feel.

---

## 3. End-to-End Streaming Flow (This Repo)

```
User type → ChatComposer @send → pages/index.vue handleSend()
  → stores/chat.ts sendMessage() pushes streamMsg {streaming:true, text:''}
  → api/index.ts fetch POST /api/chat/query/stream (AbortSignal)
  → FastAPI chat.py StreamingResponse(event_stream())
  → rag.py stream_answer(): get_graph().run(State, Deps) → agent.run_stream(..., deps)
  → for delta in result.stream_text(delta=True): yield text_delta (true deltas)
  → chat.py formats data: {"content": delta}\n\n, event: done/sources
  → frontend reader loop: onDelta → streamMsg.text += delta (reactive)
  → pages/index.vue: skeleton inside bubble → Comark markdown streams
  → onDone: streamMsg.streaming=false, conv.id swap if first turn
```

Earlier bug was `stream_text()` without `delta=True` → each `data:` carried the full accumulated answer → `+=` doubling. Fixed at `rag.py:253`.

Remaining buffered-at-once symptom is caused by `GZipMiddleware` at `app/main.py:82` — bypass for `/api/chat/query/stream` restores chunked delivery.

---

## 4. Verification Checklist

*   `ruff check app/services/rag.py app/main.py app/api/chat.py`
*   `vue-tsc --noEmit` (single-bubble template)
*   `tests/test_chat_stream.py` — uses `TestModel` + `TestClient` + `stream_text(delta=True)` → asserts `data: {"content":` + `event: sources` + `event: done`
*   Manual: English `What documents do you have?` → single VeilAi bubble skeleton → English wrapper streams token-by-token + Vietnamese titles verbatim (rule 8 language-matched); Vietnamese query → same in Vietnamese. Network tab `query/stream` shows incremental `data:` lines with `transfer-encoding: chunked` and no `content-encoding: gzip`.

## Sources

*   `https://ai.pydantic.dev/` (llms.txt index) — `Agent.run_stream` / `StreamedRunResult`
*   `backend/.venv/Lib/site-packages/pydantic_ai/result.py:617` — `stream_text(delta=...)` contract
*   `backend/app/services/rag.py:223`, `backend/app/api/chat.py:60`, `backend/app/main.py:82`, `frontend/src/api/index.ts:23`, `frontend/src/stores/chat.ts:164`, `frontend/src/pages/index.vue:103`, `frontend/vite.config.ts:27`
*   `https://ui.nuxt.com/getting-started` (Nuxt UI v4 built on Reka UI + Tailwind, 125+ components, Vue/Vite auto-imports)
*   `https://vuejs.org/api/reactivity-core.html` (ref/reactive proxy for Pinia)
*   SSE spec `text/event-stream` (`event:` + `data:` + blank line)
*   Starlette `GZipMiddleware` buffering of `StreamingResponse` (primary FastAPI/Starlette docs)
