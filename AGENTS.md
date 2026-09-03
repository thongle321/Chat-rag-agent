# AGENTS.md — chat-rag-agent

> Context file auto-loaded by `pi` (and Claude Code). Keep this concise but complete — agents read it on every turn.

## Project Overview

**Document RAG Chatbot + Product Recommendations** — private knowledge-base assistant with hybrid retrieval, streaming answers, citations, ChatGPT-style product cards, and omnichannel integrations (Facebook, Zalo).

- **Backend:** Python 3.11+ / FastAPI + `pydantic-ai` (agent), ChromaDB (vectors), BM25s + RRF (hybrid), FastEmbed `intfloat/multilingual-e5-small`, SQLAlchemy + aiosqlite, `fastapi-users` (JWT, roles `user`/`admin`), Logfire
- **Frontend:** Vue 3 + Vite + `vue-router` + Pinia + `@nuxt/ui` + Tailwind 4 + Axios + `fetch` streaming (chat-vue template patterns: `UDashboardSidebar 15rem`, `useChats`/`useChatActions`, `view-transition-name:chat-prompt`)
- **Storage:** `backend/data/app.db` single-tenant (users, sessions, unified tables, logs, products — no `tenant_id`), `backend/.chromadb/` (vectors), `backend/data/uploads/` (originals), `backend/data/bm25_index/` (BM25). No `conversations.db` (legacy removed).
- **Default admin:** `admin@example.com` / `admin123` (seeded in `lifespan`)

## Repository Structure

```
backend/
  app/
    main.py              # FastAPI app, lifespan (DB create, admin seed, AI settings hot-reload), middleware
    retrieval.py         # ChromaRetrieval: vector × BM25 → RRF fusion + distance gate
    core/
      config.py          # Settings (pydantic-settings, .env) — single source of truth
      middleware.py      # SecurityHeadersMiddleware, NoGzipForSSE
    db/
      session.py         # async_engine (sqlite+aiosqlite://data/app.db), create_db_and_tables
      vector_store.py    # Chroma PersistentClient wrapper, BM25 build, RRF
      embeddings.py      # FastEmbed wrapper + e5 prefix (blocking — always asyncio.to_thread)
      conversation_store.py # ORM message history on app.db (ModelMessagesTypeAdapter, raw_data)
    models/
      user.py            # User (fastapi-users, role=user|admin), Base
      session.py         # ChatSession
      unified.py         # Channel/Conversation/Message/Document/DocumentChunk/AppSetting/SyncLog/AIUsageLog/Product
      chat_logging.py    # ActivityLog + ChatMessageLog (durable logs)
      schemas.py         # ChatRequest/Response, DocumentInfo, etc.
    services/
      rag.py             # _run_agent / stream_answer / answer_question — RAG + search_products tools
      products.py        # Product catalog: search (embedding cosine, PRODUCT_SCORE_GATE=0.30 pre-slice), ShopifySource/CsvSource, upsert via _dedupe_stmt
      llm.py             # get_llm() → (model, model_name) per ai_provider (openai/ollama)
      document_ingest.py # chonkie chunking + save_and_queue_indexing + index_file
      document_status.py / chat_logging.py / encryption.py / ai_settings.py
      facebook_channels.py / zalo_channels.py / user_manager.py  # require_admin/require_user, current_admin_user/current_user_user
    api/
      routes.py          # central /api router
      auth.py            # JWT login/register + /me
      chat.py            # POST /chat/query, /chat/query/stream (SSE via _SSE_FIELDS+_format_sse); _decode_bearer decodes pyjwt once (no jose dep)
      sessions.py        # chat session CRUD
      docs.py            # POST /documents/upload, GET, DELETE /{title} (admin-only)
      products.py        # GET/POST/PUT/DELETE /products (admin), POST /import-csv, POST /sync-shopify, GET /search (public)
      settings.py / stats.py / health.py / logs.py   # admin-only (settings/stats/docs/facebook/zalo)
      facebook.py / zalo.py  # webhook, channels, sync
  data/ / .chromadb/ / .venv / pyproject.toml / uv.lock / .env
frontend/
  vite.config.ts         # port 3000, proxy /api → localhost:8000
  src/
    main.ts / App.vue / layouts/default.vue
    api/index.ts         # axios + streamChat (SSE via fetch, forwards JWT; StreamProduct/StreamHandlers)
    stores/ chat.ts (products/followups per message) / auth.ts / documents.ts / settings.ts
    composables/ useChats.ts / useChatActions.ts
    components/ ChatSidebar.vue / ChatComposer.vue / UserMenu.vue
    components/chat/ Indicator.vue / SourceLink.vue / ProductCard.vue / ModelSelect.vue
    pages/ index.vue (public chat: title dropdown, thinking timer, hover edit, ProductCards+chips), admin/products.vue, admin/*, login.vue
  package.json / pnpm-lock.yaml / biome.json / vercel.json
docs/research/  bilingual-rag.md, chat-vue-template.md, cqa-db-design-for-rag.md, etc.
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
```

## Environment Variables

`backend/.env` (loaded by `Settings` in `app/core/config.py`):

```
ENVIRONMENT=development
OPENAI_API_KEY / OLLAMA_API_KEY / OLLAMA_BASE_URL / HF_TOKEN / LOGFIRE_TOKEN
JWT_SECRET_KEY            # required in production (lifespan asserts)
ENCRYPTION_KEY            # base64 or plain, for channel tokens
```

Key `Settings` fields: `ai_provider` (`ollama`|`openai`), `openai_model` (`gpt-5.5`), `ollama_model` (`gemma4:31b-cloud`), `ollama_base_url`, `embedding_model`, `retrieval_k=8`, `retrieval_rrf_k=60`, `retrieval_bm25_overretrieve=2`, `retrieval_distance_threshold=None`, `context_prompt`.

## API Map

All under `/api` (`app/api/routes.py`):

| Prefix | Module | Key routes |
|--------|--------|------------|
| `/auth` | `auth.py` | `POST /auth/jwt/login`, `/auth/jwt/logout`, `POST /auth/register`, `GET /auth/me` |
| `/health` | `health.py` | `GET /health` |
| `/settings` | `settings.py` | AI provider/model CRUD (admin) |
| `/stats` | `stats.py` | usage stats (admin) |
| `/documents` | `docs.py` | `POST /upload` (multipart, 50MB limit, background `index_file`), `GET /`, `DELETE /{title}`, `GET /status` (admin) |
| `/products` | `products.py` | `GET /` list, `POST /`, `PUT /{id}`, `DELETE /{id}` (admin); `POST /import-csv` (admin); `POST /sync-shopify` (admin); `GET /search?q=&k=` (public) |
| `/chat` | `chat.py` + `sessions.py` | `POST /query` (non-stream), `POST /query/stream` (SSE), session list/get/delete |
| `/logs` | `logs.py` | activity + chat logs (admin) |
| `/facebook` | `facebook.py` | webhook verify, message handling, channel mgmt (admin) |
| `/zalo` | `zalo.py` | Zalo webhook + channel mgmt (admin) |

**Auth model:** `/` chat is public like ChatGPT (anonymous allowed, `_optional_user_with_email` enriches logs). Admin (`role=admin`) is redirected to `/admin/` and cannot use user chat; user (`role=user`) cannot access `/admin` or admin APIs. Backend enforces via `require_admin`→`current_admin_user` (docs/settings/facebook/zalo/stats/products-admin) vs public/best-effort (chat/sessions/products-search). Frontend guards are UX only.

**Streaming protocol** (`POST /chat/query/stream`): SSE `data: {"content": "..."}` deltas, `event: sources` + `event: products` (`{products: StreamProduct[]}`) + `event: followups` (`{followups: string[]}`) + `event: done` (`{session_id, model}`), `event: error`. GZip bypassed for this path (`NoGzipForSSE`).

## RAG + Commerce Pipeline

`app/services/rag.py` + `app/retrieval.py` + `app/services/products.py`:

1. `get_retrieval().search(query, k=8)` — embed query (e5 prefix) → over-retrieve vectors (`k*over`), build BM25 ranks (`_ensure_bm25()`), RRF-fuse, optional `retrieval_distance_threshold` gate.
2. `Deps` + `search_documents` / `search_products` tools (pydantic-ai) — agent calls per intent; catalog injected into `system_prompt` (+ SHOPPING RULES 9/10/11: only `[P1]`-cited SKUs, vague queries → 2-3 clarifying `?` lines, honest sales line); `ProcessHistory(_keep_recent)` caps history to 10, `ReinjectSystemPrompt` refreshes catalog.
3. `stream_answer()` — creates/fetches `conversation_id`, runs `agent.run_stream`, yields `text_delta`, persists citation stubs (`metadata.sources` on `ModelResponse`), saves to `conversation_store`, durable logs via `chat_logging` (user + assistant + `activity_logs`), token usage captured. Emits `products` (only `[P1]`-cited) + `followups` (only when `products_searched` and nothing cited, budget/category/dietary preferred).
4. Citations: only numbers actually present in answer (`\[(\d+)\]` / `\[P(\d+)\]`) are surfaced; doc metadata hydrated at read-time from vector store so renames/deletes reflect immediately. Product search: embedding cosine over active products via `asyncio.to_thread` (FastEmbed is blocking), `PRODUCT_SCORE_GATE=0.30` applied pre-slice (sorted desc, `break` on first miss); LIKE fallback on embedding failure needs 2 token hits for multi-word queries (1 for single-word). Followup strip is bullet-only (`[\u2022-]|\d+[.)]` + whitespace) so prices like `2 for $10?` survive.
5. Ingest: `ProductSource` protocol — `ShopifySource` (Admin API `products.json`, storefront URL `https://{domain}/products/{handle}`) + `CsvSource` (name,description,price,currency,image_url,product_url,category,stock,sku) + manual CRUD; `upsert_products` dedupes via `_dedupe_stmt`: `(source,external_id)` → `sku` → `name` (name fallback scoped by `source` when present).

## Conventions

### Python (backend)

- **Formatter/lint:** `ruff` (line-length 120, target `py311`, rules `E,F,I,B,UP`). Run `uv run ruff check app/ && uv run ruff format --check app/`.
- **Imports:** top-level only, `isort` via ruff `I`. Absolute `app.*` imports.
- **Async:** `AsyncSession` + `async_session_factory`; blocking work (Chroma/BM25/FastEmbed) via `asyncio.to_thread`.
- **Config:** never hardcode secrets/hosts — use `app.core.config.settings`. DB paths relative to `backend/data`.
- **Auth:** `fastapi-users` — `current_admin_user` / `current_user_user`; chat endpoints are best-effort auth (anonymous allowed, Bearer token enriches logs).
- **Logging:** `logfire` instrumented (fastapi, httpx, sqlalchemy, pydantic-ai); use `logger` + `log_activity`/`log_chat_message`.

### Frontend (Vue)

- **Lint/format:** `@biomejs/biome` (`biome.json` — `noExplicitAny: off`, etc.). Don't use `eslint`.
- **Style:** Tailwind 4, `@nuxt/ui` auto-imports (`vue`, `vue-router`, `@vueuse/core`). `<script setup lang="ts">`, `i-lucide-*` icons only.
- **State:** Pinia stores (`chat.ts` etc.); chat persistence in `localStorage` + server sessions. Streaming via `streamChat()` in `api/index.ts` (native `fetch`, not axios, to read SSE). Shared `StreamProduct` type in `api/index.ts`, imported by `ProductCard.vue`/`chat.ts`.
- **Routing:** `vue-router/vite` file-based (`src/pages/*` → routes, `route-map.d.ts` generated). `/` public chat, `/login` user, `/admin/*` admin-only.
- **API:** `api` (axios) base `VITE_API_URL || "/api"`; streaming path manually adds `Authorization: Bearer <auth_token>` from `localStorage`.

### General

- Don't commit `.env`, `.chromadb/`, `data/*.db`, `uploads/`, `bm25_index/`, `.venv/`, `node_modules/`, `dist/`.
- Keep `AGENTS.md` concise; detailed design notes go in `docs/research/*.md`.
- Tests: `backend/tests/test_chat_stream.py` (extend with `pytest` + `httpx`).

## Useful Commands (agents)

```bash
# backend
uv sync && uv run ruff check app/ && uv run ruff format --check app/
uv run pytest -q
uv run fastapi dev app/main.py

# frontend
pnpm install && pnpm build && pnpm dev
npx biome check src/
```

## Gotchas

- `backend/.env` must exist — `JWT_SECRET_KEY` required or `lifespan` raises.
- Chroma `PersistentClient` **and FastEmbed** are blocking — always wrap in `asyncio.to_thread`.
- SSE stream must not be GZipped (`NoGzipForSSE`); don't add global compression that re-enables it.
- Single DB `data/app.db` (`Base.metadata.create_all`, fresh, no migrations); no `tenant_id` anywhere; vectors stay in `.chromadb`, BM25 derived.
- Frontend `VITE_API_URL` trailing `/api` matters (`api/index.ts` appends `/chat/...`).
- Zalo: global `zalo_webhook_url` in settings vs per-channel `bot_token` + `verify_token` (8..256) in integrations.
