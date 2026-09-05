# AGENTS.md — chat-rag-agent

> Context file auto-loaded by `pi` (and Claude Code). Keep this concise but complete — agents read it on every turn.

## Project Overview

**Document RAG Chatbot + Product Recommendations** — private knowledge-base assistant with hybrid retrieval, streaming answers, citations, ChatGPT-style product cards, and omnichannel integrations (Facebook, Zalo).

- **Backend:** Python 3.11+ / FastAPI + `pydantic-ai` (agent), ChromaDB (vectors), BM25s + RRF (hybrid), FastEmbed `intfloat/multilingual-e5-small` (custom ONNX registration + e5 `query:`/`passage:` prefixes), SQLAlchemy + aiosqlite, `fastapi-users` (JWT 3600s, argon2 via `pwdlib`, roles `user`/`admin`), Logfire, `liteparse` + `chonkie` ingest, `python-zalo-bot`
- **Frontend:** Vue 3 + Vite + `vue-router` (file-based via `vue-router/vite`, `route-map.d.ts`) + Pinia + `@nuxt/ui` + Tailwind 4 + Axios + `fetch` streaming
- **Storage:** `backend/data/app.db` single-tenant (users, sessions, unified tables, logs, products — no `tenant_id`), `backend/.chromadb/` (vectors), `backend/data/uploads/` (originals). BM25 derived in-vector-store. No `conversations.db` (legacy removed).
- **Default admin:** `admin@example.com` / `admin123` (seeded in `lifespan`)

## Repository Structure

```
backend/
  app/
    main.py              # FastAPI app ("VeilAi Rag"), lifespan (JWT assert, DB create, admin seed, AI+zalo settings hot-reload), NoGzipForSSE lives here
    retrieval.py         # ChromaRetrieval.search owns RRF fusion: embed → over-retrieve → bm25_ranks → RRF → gate → fetch
    core/
      config.py          # Settings (pydantic-settings, backend/.env) — single source of truth
      middleware.py      # SecurityHeadersMiddleware only (CSP per path class)
    db/
      session.py         # async_engine (sqlite+aiosqlite://data/app.db), create_db_and_tables, get_async_session/get_user_db
      vector_store.py    # Chroma PersistentClient wrapper; storage primitives query(where pushdown)/bm25_ranks/fetch + rrf()/fuse_ranks() (official 1/(k+rank)); list/count/add/upsert/delete_ids/get_metadata (no hybrid_query — fusion lives in retrieval.py)
      embeddings.py      # FastEmbed wrapper, custom-model registry, query_prefix()/passage_prefix() (blocking — always asyncio.to_thread)
      conversation_store.py # ORM message history on app.db (load/save/delete_conversation/close)
    models/
      user.py            # Base + User (fastapi-users UUID, role=user|admin)
      session.py         # ChatSession (id, user_id NULL=anon, title, pinned)
      unified.py         # Channel/Conversation/Message/Document/DocumentChunk/AppSetting/SyncLog/AIUsageLog/Product
      facebook_channel.py # FacebookChannelModel (table facebook_channels, page_id/token/verify_token/slug)
      zalo_channel.py    # ZaloChannelModel (table zalo_channels, bot_id/token/verify_token/webhook_url/slug)
      chat_logging.py    # ActivityLog + ChatMessageLog (durable logs)
      ai_settings.py / document_status.py  # settings mirror, PENDING/PROCESSING/COMPLETED/FAILED
      schemas.py         # ChatRequest (≤2000 chars)/Response, DocumentInfo, SessionListItem/Patch/Detail, StatsResponse
    services/
      rag.py             # stream_answer / answer_question — RAG + search_products/search_shopify_catalog tools, citation stubs, followups, durable logs
      products.py        # search_products (hybrid RRF + distance gate over products collection, hydrates from chunk meta), CRUD write-through sync, CsvSource ingest, upsert via _dedupe_stmt
      llm.py             # get_llm() → (model, model_name) per ai_provider (openai/ollama), cached per provider:model
      document_ingest.py # liteparse (cheap + OCR vie+eng dpi=400) + chonkie RecursiveChunker (char, 1200/24) + LLM Title:/Reference: + batch-500 add
      document_status.py / chat_logging.py / encryption.py / ai_settings.py (KV save/load)
      shopify_global.py  # Global Catalog MCP over direct HTTPS (no key; endpoint+profile+catalog_id in app_settings KV, never persists results)
      facebook_channels.py / zalo_channels.py / user_manager.py  # require_admin/require_user, current_admin_user/current_user_user/current_active_user
    api/
      routes.py          # central /api router
      auth.py            # fastapi-users routers: POST /login (form-data username/password), POST /logout, POST /register, GET /me
      chat.py            # POST /chat/query, /chat/query/stream (SSE via _SSE_FIELDS+_format_sse); _decode_bearer (pyjwt, no jose)
      sessions.py        # GET /sessions (own, auth), GET /sessions/:id (public + FB-PSID fallback), PATCH (owner-scoped, claims anon), DELETE (owner-scoped 404)
      docs.py            # POST /documents/upload (multi-file `files`, 50MB each, background index_file), GET "" list, DELETE /{title}, GET /upload/status?titles= (poll)
      products.py        # GET / (admin list all), GET /search?q=&k= (public), POST /, PUT /{pid}, DELETE /{pid}, POST /import-csv (admin)
      settings.py        # GET+PUT /settings/ai, POST /settings/test, POST /settings/models (admin; ollama local /api/tags vs cloud /models)
      stats.py           # GET /stats (admin; bounded 500-session query scan)
      health.py          # GET /health, GET /health/detailed (vector_store component)
      logs.py            # GET /logs/chat-logs + /logs/activity-logs (auth required; non-admin sees own only; paginated)
      facebook.py / zalo.py  # webhook, channels, sync
  data/ / .chromadb/ / .env / .env.example / pyproject.toml / uv.lock
frontend/
  vite.config.ts         # port 3000, proxy /api → localhost:8000, @nuxt/ui (neutral=slate, primary=blue)
  src/
    main.ts / App.vue / layouts/default.vue / route-map.d.ts
    api/index.ts         # axios (180s timeout, JWT + 401/403 redirect interceptors, getErrorMessage) + streamChat (SSE via fetch; StreamSource/StreamProduct/StreamHandlers)
    stores/ chat.ts (anon-temp bucket, identity buckets, hydrating/prefetch, per-conv AbortController, id-swap onDone) / auth.ts (form-data login, syncChatBucket, boot fetchUser) / documents.ts / settings.ts
    composables/ useChats.ts / useChatActions.ts
    components/ AppLogo.vue / ChatSidebar.vue / ChatComposer.vue / ChatEmpty.vue / ChatView.vue (shared surface: sessionId prop, ready gate, not-found emit) / ModelSelect.vue / UserMenu.vue
    components/chat/ Indicator.vue / SourceLink.vue / ProductCard.vue
    pages/ index.vue (:session-id=null + clearActive), c/[id].vue (:key + replace('/') on unknown), login.vue, 404.vue, [...all].vue, admin.vue (layout),
           admin/index.vue, admin/documents.vue, admin/products.vue (local CRUD + CSV import w/ result toast + Shopify Global Catalog modal: Enabled/endpoint/profile_url/catalog_id, Save/Test w/ toasts, Save closes), admin/settings.vue, admin/login.vue,
           admin/integrations/index.vue, admin/integrations/[id].vue, admin/integrations/zalo/[id].vue,
           admin/messages/index.vue, admin/messages/[id].vue
    utils/ routeAccess.ts  # deny-list: only /admin* gated (/admin/login public); substring-match ADMIN_ONLY_DETAIL/ADMIN_NO_CHAT_DETAIL + redirectForStatus
  package.json (scripts: build/dev/preview only; deps: @comark/vue, @iconify-json/lucide, @nuxt/ui, @unhead/vue, axios, pinia, vue, vue-router, zod; node 24.x) / biome.json / vercel.json
docs/research/  bilingual-rag.md, chat-quality-agent-production-logging.md, chat-vue-template.md, chatgpt-shopping-replication.md, citation-persistence.md, cqa-db-design-for-rag.md, ecommerce-rag-lessons.md, gated-retrieval-vs-reranking.md, integrations-facebook-feature.md, per-user-session-storage.md, product-search-complexity-review.md, search-functionality-comparison.md, shopify-global-catalog.md, shopify-store-connect.md, streaming-llm-frontend.md, zalo-integration.md, zalo-refactor-webhook-sdk.md
```

## Running Locally

### Backend

```bash
cd backend
uv sync                  # or pip install -e .
# .env required — see .env.example (JWT_SECRET_KEY, ENCRYPTION_KEY mandatory)
fastapi dev app/main.py  # auto-reload :8000
# or
uv run fastapi dev app/main.py
uv run uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
pnpm install
pnpm dev      # :3000 (proxies /api to :8000)
pnpm build    # vite build
pnpm preview
```

- Frontend uses `import.meta.env.VITE_API_URL || "/api"` — dev needs no `.env`; prod set `VITE_API_URL`.
- CORS allows `http://localhost:3000` (see `main.py`).

### Health Check

```
GET /              → { message, environment, version }
GET /api/health    → { status: "ok", version, environment }
GET /api/health/detailed → { status, components: { vector_store, vector_store_count } }
```

## Environment Variables

`backend/.env` (loaded by `Settings` in `app/core/config.py`, `env_file=backend/.env`):

```
ENVIRONMENT=production
OPENAI_API_KEY / OLLAMA_API_KEY / OLLAMA_BASE_URL / HF_TOKEN / LOGFIRE_TOKEN
JWT_SECRET_KEY            # always asserted in lifespan (dev included)
ENCRYPTION_KEY            # base64 or plain, for channel tokens
```

Key `Settings` fields: `app_name="VeilAi Rag"`, `ai_provider` (`ollama`|`openai`), `openai_model` (`gpt-5.5`), `ollama_model` (`gemma4:31b-cloud`), `ollama_base_url` (`https://ollama.com/v1`, `/api` suffix stripped on save), `ollama_api_key`, `embedding_model`, `retrieval_k=8`, `retrieval_rrf_k=60`, `retrieval_bm25_overretrieve=2`, `retrieval_distance_threshold=None`, `context_prompt`, `zalo_api_key`/`zalo_verify_token` (kept in sync, auto-generated when empty) + `zalo_webhook_url`. AI+zalo settings hot-reload from `app_settings` KV in `lifespan`, persisted via `save_ai_settings`.

## API Map

All under `/api` (`app/api/routes.py`):

| Prefix | Module | Key routes |
|--------|--------|------------|
| `/auth` | `auth.py` | `POST /login` (form-data `username`+`password`), `POST /logout`, `POST /register`, `GET /me` |
| `/health` | `health.py` | `GET /` (public), `GET /detailed` |
| `/settings` | `settings.py` | `GET+PUT /ai`, `POST /test`, `POST /models`, `GET+PUT /shopify-catalog`, `POST /shopify-catalog/test` (all admin) |
| `/stats` | `stats.py` | `GET /` = `/api/stats` (admin) |
| `/documents` | `docs.py` | `POST /upload` (field `files`, list, 50MB/file, background `index_file`), `GET /` (="" no trailing slash), `DELETE /{title}`, `GET /upload/status?titles=a,b` (all admin) |
| `/products` | `products.py` | `GET /` list all (admin), `GET /search?q=&k=` (public), `POST /`, `PUT /{pid}`, `DELETE /{pid}`, `POST /import-csv` (admin) |
| `/chat` | `chat.py` + `sessions.py` | `POST /query` (non-stream), `POST /query/stream` (SSE), `GET /sessions` (own list, auth), `GET /sessions/:id` (public + FB-PSID fallback), `PATCH /sessions/:id` (title/pin, owner-scoped, claims anon), `DELETE` (owner-scoped 404) |
| `/logs` | `logs.py` | `GET /chat-logs`, `GET /activity-logs` (auth required; non-admin scoped to own; `?page&per_page&session_id/role/action`) |
| `/facebook` | `facebook.py` | webhook verify, message handling, channel mgmt (admin) |
| `/zalo` | `zalo.py` | Zalo webhook + channel mgmt (admin) |

**Auth model:** `/` chat is public like ChatGPT (anonymous allowed, `_optional_user_with_email` enriches logs). Strict role isolation, backend is source of truth: admin (`role=admin` or `is_superuser`) is redirected to `/admin/` and cannot use user chat (`require_user` 403s); `require_admin` 403s non-admins. Guards: `current_admin_user` (docs/settings/stats/products-admin/facebook/zalo) vs `current_active_user` (logs — any authed user, scoped) vs public/best-effort (chat, session-detail, products-search). Frontend guards (`main.ts` + `routeAccess.ts`) are UX only; axios + `streamChat` share `redirectForStatus` (401 drops token, 403 keeps it).

**Streaming protocol** (`POST /chat/query/stream`): single `_SSE_FIELDS` dispatch → `data: {"content": "..."}` deltas, `event: sources` + `event: products` (`{products: StreamProduct[]}`) + `event: followups` (`{followups: string[]}`) + `event: done` (`{session_id, model}`), `event: error` (`{detail, status_code}`). GZip bypassed for this path (`NoGzipForSSE` in `main.py`).

## RAG + Commerce Pipeline

`app/services/rag.py` + `app/retrieval.py` + `app/services/products.py`:

1. `get_retrieval().search(query, k=8)` — embed query (e5 `query:` prefix) → over-retrieve vectors (`k*over`), BM25 ranks (`store.bm25_ranks()`), `_rrf` fuse, optional `retrieval_distance_threshold` gate on vector distance, hydrate via `store.fetch()`.
2. `Deps` + `search_documents` / `search_products` / `search_shopify_catalog` tools (pydantic-ai) — agent calls per intent; doc catalog + SHOPPING RULES 9/10/11/13 injected into `system_prompt` (only `[P1]`-cited SKUs; local catalog first, Global Catalog when local misses or user wants wider choice, shared `[Pn]` numbering); `ProcessHistory(_keep_recent)` caps history to 10 (drops leading orphan responses), `ReinjectSystemPrompt` refreshes catalog. `UsageLimits(request_limit=3)`; 120s agent + stream timeouts; provider-misconfig → 502 hint.
3. `stream_answer()` — loads history via `conversation_store`, runs `agent.run_stream`, yields `text_delta`, persists citation stubs (`metadata.sources` chunk-ids on the last `ModelResponse`), saves `history + new_messages`, durable logs (`log_chat_message` user+assistant with tokens/latency/model + `log_activity chat.query`). Emits `products` (only `[P1]`-cited) + `followups` (only when `products_searched` and nothing cited, budget/category/dietary preferred).
4. Citations: only numbers actually present in answer (`\[(\d+)\]` / `\[P(\d+)\]`) are surfaced; doc metadata hydrated at read-time from vector store so renames/deletes reflect immediately. Product search: hybrid RRF over the `products` collection (dense over-retrieve + `bm25_ranks`, `fuse_ranks` = official `1/(k+rank)` k=60, `PRODUCT_DISTANCE_GATE=0.70` on cosine distance — the old SQL-scan gate was cosine similarity ≥ 0.30), `category` pushed into dense `query(where=)` pre-fusion (+ Python post-filter for BM25 strays), `max_price` post-filter on chunk metadata (priceless rows excluded when gated), deterministic re-rank (in-stock → category-overlap → fusion score); display fields hydrate from the index so SQL is never scanned and the embedding-failure LIKE fallback is gone. Followup strip is bullet-only (`[•-]|\d+[.)]` + whitespace) so prices like `2 for $10?` survive.
5. Ingest: `save_and_queue_indexing` (overwrite deletes old doc + PENDING status) → `index_file` (background): liteparse cheap-parse, OCR (`vie+eng`, dpi=400) when any page `needs_ocr`, images always OCR; chonkie char-chunker; LLM `Title:`/`Reference:` summary (60s timeout, failure → filename); batch-500 `store.add`; COMPLETED/FAILED status. Product ingest: `ProductSource` protocol — `CsvSource` (columns name,description,price,currency,image_url,product_url,category,stock,sku; only **name+price required**, imageless rows import and render text-only) + manual CRUD; every write path (`create/update/delete/import-csv` via `sync_products_to_index`/`remove_product_from_index`, chunk id `product:{uuid}`) write-through syncs the `products` collection (upsert active, drop inactive/deleted; SQL commits first, index failure only logs). `POST /import-csv` returns `{imported, skipped}` (skipped = rows missing name/price) and the Products page toasts the result. Global Catalog (`shopify_global.py`, `POST https://catalog.shopify.com/api/ucp/mcp`, profile-URL auth, no key) is live-search only and never saved: fetch-wide (`fetch_limit=50`) + local e5-cosine re-rank to 6 (fail-open keeps Shopify order). `upsert_products` dedupes via `_dedupe_stmt`: `(source,external_id)` → `sku` → `name` (scoped by `source` when present).

## Conventions

### Python (backend)

- **Formatter/lint:** `ruff` (line-length 120, target `py311`, rules `E,F,I,B,UP`). Run `uv run ruff check app/ && uv run ruff format --check app/`.
- **Imports:** top-level only, `isort` via ruff `I`. Absolute `app.*` imports.
- **Async:** `AsyncSession` + `async_session_factory`; blocking work (Chroma/BM25/FastEmbed) via `asyncio.to_thread`.
- **Config:** never hardcode secrets/hosts — use `app.core.config.settings`. DB paths relative to `backend/data`.
- **Auth:** `fastapi-users` — `current_admin_user` / `current_user_user` / `current_active_user`; chat endpoints are best-effort auth (anonymous allowed, Bearer token enriches logs).
- **Logging:** `logfire` instrumented (fastapi, httpx, sqlalchemy, pydantic-ai); use `logger` + `log_activity`/`log_chat_message`.

### Frontend (Vue)

- **Lint/format:** `@biomejs/biome` (`biome.json` — `noExplicitAny: off`, etc.). Don't use `eslint`.
- **Style:** Tailwind 4, `@nuxt/ui` auto-imports (`vue`, `vue-router`, `@vueuse/core`). `<script setup lang="ts">`, `i-lucide-*` icons only.
- **State:** Pinia stores. Sessions are per-account like ChatGPT: `ChatSession.user_id` (NULL = anonymous), `_ensure_session` claims pre-login rows, PATCH claims owner-less rows; sidebar source is `GET /chat/sessions` after login. `localStorage` bucketed per account (`chat_sessions:user:<id>`); logged-out is temporary-chat mode — `saveToStorage` no-ops and `cleanupGuestKeys` drops legacy/anon keys (sidebar empty when anon). `switchIdentity` + `loadServerSessions` in `chat.ts`, called from `auth.ts` login/logout/boot-`fetchUser`. In-flight streams survive route remounts (in-memory cache) and chat switches (per-conversation `AbortController`); first `onDone` swaps local id → server `session_id`. Rename/pin PATCH-sync (authed only). Streaming via `streamChat()` in `api/index.ts` (native `fetch`, not axios, to read SSE; forwards `auth_token` JWT manually). Shared `StreamProduct`/`StreamSource`/`StreamHandlers` types in `api/index.ts`, imported by `ProductCard.vue`/`chat.ts`.
- **Routing:** file-based (`src/pages/*` → routes, `route-map.d.ts` generated). `/` always blank composer (`clearActive`, conversation created on first send → id-swap, no push); direct `/c/:id` validates via `chat.ts:resolveSession` (local → `GET /chat/sessions/:id` → hydrate, 404→false→`replace('/')`); delete-open → `replace('/')`; back/forward via `:key`. Deny-list only (`utils/routeAccess.ts` — `/admin*` gated with `/admin/login` public, everything else public incl. `/c/`); axios interceptor + `streamChat` + `main.ts` guard share `redirectForStatus`. Sidebar uses real `to: /c/:id` links (single-click + middle-click). `useChats`/`useChatActions` composables wrap the store. `prefetchSession` (hover/focus, `hydrating` dedupe + skeleton) warms message cache.
- **Header auth:** logged-out shows Log in (ghost → `/login`) + Sign up (solid → `/login?mode=signup`); logged-in shows nothing (sidebar footer only). Per-message `Thought for Xs` kept.
- **API:** `api` (axios) base `VITE_API_URL || "/api"`, 180s timeout; login posts form-data (`username`+`password`) to `/auth/login`.

### General

- Don't commit `.env`, `.chromadb/`, `data/*.db`, `uploads/`, `.venv/`, `node_modules/`, `dist/`.
- Keep `AGENTS.md` concise; detailed design notes go in `docs/research/*.md`.
- No backend test suite currently (`backend/tests/` does not exist).

## Useful Commands (agents)

```bash
# backend
uv sync && uv run ruff check app/ && uv run ruff format --check app/
uv run fastapi dev app/main.py

# frontend
pnpm install && pnpm build && pnpm dev
npx biome check src/
```

## Gotchas

- `backend/.env` must exist — `lifespan` raises when `JWT_SECRET_KEY` is unset (dev included).
- Chroma `PersistentClient` **and FastEmbed** are blocking — always wrap in `asyncio.to_thread`.
- SSE stream must not be GZipped (`NoGzipForSSE` in `main.py`); don't add global compression that re-enables it.
- Single DB `data/app.db` (`Base.metadata.create_all`, fresh, no migrations); no `tenant_id` anywhere; vectors stay in `.chromadb`, BM25 derived. `facebook_channels`/`zalo_channels` tables are separate from unified `channels`.
- Frontend `VITE_API_URL` trailing `/api` matters (`api/index.ts` appends `/chat/...`).
- Zalo: global `zalo_verify_token` (+ legacy `zalo_api_key` alias) and `zalo_webhook_url` in Settings/admin-settings vs per-channel `bot_token` + `verify_token` in integrations.
- Sidebar double-click bug (root-caused, fix pending): hover shows pointer but first click swallowed, URL stays `/`. Cause is NOT Vue/Reka/handlers — `document.body.style.pointerEvents === 'none'` (INLINE style, no stylesheet rule) on `<body>`, so renderer paints everything but hit-tests only `<HTML>`. Prime suspect: `UDashboardSidebar` drawer/Menu overlay locking body pointer-events on open and never restoring. Diagnose via `getComputedStyle` pointerEvents chain + CDP `DOM.getNodeForLocation`; repro needs real CDP input (`page.click`) — programmatic `el.click()` bypasses hit-testing and misleads.
- `isPublicPath` uses `startsWith("/admin")` — over-matches `/administrator`; harden to segment boundary (`/admin` exact or `/admin/` prefix) when touched. `routeAccess` matches backend 403 details by substring — update constants if backend rewords them.
- Browser automation: Helium `chrome.exe --remote-debugging-port=9222`; `browser-eval.js` picks `.at(-1)` which can land on the extension background page — always target the tab by URL (`localhost:3000`).
