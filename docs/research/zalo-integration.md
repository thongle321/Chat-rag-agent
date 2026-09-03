# Zalo Bot Integration Research — chat-rag-agent

Date: 2026-09-01
Scope: Create a Zalo integration for chat-rag-agent where user already has a Zalo Bot (bot.zapps.me). Primary sources only — official docs at bot.zapps.me/docs and first-party codebase. Align shape with existing Facebook integration.

## Summary

Your `chat-rag-agent` already ships a production Facebook pattern: multi-channel CRUD (`page_id` unique, `slug`, encrypted `page_token`), webhook verification (`hub.mode` challenge), `POST /webhook` → `answer_question` → `send_message`, health check, paginated backfill sync, and `conversation_store` (`facebook_conversation_links`, `facebook_sync_logs`). Zalo Bot at `bot.zapps.me` is a **different product** from legacy Zalo OA (`developers.zalo.me`/`openapi.zalo.me`): it is a Telegram-style Bot API with a single long-lived `Bot Token` (`123456:abc-xyz`) embedded in the URL `https://bot-api.zaloplatforms.com/bot${TOKEN}/<method>`, no OAuth/refresh flow, and webhook auth via `X-Bot-Api-Secret-Token` header (not a GET challenge). Minimal Zalo build is: **new `zalo_channels` table + `POST /zalo/webhook` (header check + event dispatch) + `sendMessage` via Bot Token + `getMe` health + `setWebhook` setup** — reuse `conversation_store` (generalize or add `zalo_*` tables) and copy the Facebook `channels/{id}/health|sync` + integrations UI cards verbatim.

---

## 1. Current codebase — primary sources

* **Routing** `backend/app/api/routes.py:23-24` — `router.include_router(facebook.router, prefix="/facebook")` mounted at `/api/facebook`; add Zalo peer at `/api/zalo`.
* **Facebook API** `backend/app/api/facebook.py:36` `FB_GRAPH_API="https://graph.facebook.com/v25.0"`; `AsyncClient timeout30` `facebook.py:41-44`; `send_message` `POST /{page_id}/messages?access_token` `facebook.py:55-68`; `mark_seen`/`typing_on` `sender_action` `facebook.py:71-88`; `_health_check` probes `GET /me` then `/{page_id}?fields=id,name` `facebook.py:94-120`; `_sync_fetch_conversations` paginates `/{page_id}/conversations?fields=id,updated_time,participants` + `/{conv_id}/messages?fields=id,message,from,created_time` and maps to `ModelRequest`/`ModelResponse` into `save_messages` `facebook.py:123-210`; webhook `GET /webhook` verifies `hub.mode==subscribe && hub.verify_token ∈ tokens → challenge` `facebook.py:477-504`; `POST /webhook` filters `object=="page"`, loops `entry[].messaging[]`, skips `sender==page_id`, `asyncio.create_task(_handle_message)` `facebook.py:507-580`.
* **Channels service** `backend/app/services/facebook_channels.py:22-52` `FacebookChannelModel` single table `facebook_channels` (`id, page_id unique, page_name, page_token encrypted, verify_token, sync_interval, sync_files, last_sync_status, last_sync_at, created_at, is_active, slug`); `encrypt_token`/`decrypt_token` via `Fernet` `facebook_channels.py:149,70`; unique `page_id` check `facebook_channels.py:130-132`; slug collision loop `facebook_channels.py:135-143`; `get_channel_by_identifier` tries `id|slug|page_id` `facebook_channels.py:109-116`.
* **Model** `backend/app/models/facebook_channel.py:21-35` — `FacebookChannelModel.__tablename__="facebook_channels"` with `slug unique indexed`.
* **Encryption** `backend/app/services/encryption.py:12-26` — `_get_fernet()` derives `Fernet` from `settings.encryption_key` (44-char base64 or SHA256-derived); `encrypt_token`/`decrypt_token` handle legacy plaintext fallback `encryption.py:29-51`.
* **Conversation store** `backend/app/db/conversation_store.py:20-46` — SQLite `conversations.db` (`conversations`, `facebook_conversation_links(session_id PK, page_id, username, updated_at)`, `facebook_sync_logs`); helpers `link_page_to_session` `conversation_store.py:50-59`, `list_sessions_with_meta` `conversation_store.py:73-87`, `add_sync_log`/`list_sync_logs` `conversation_store.py:113-130`, `load_messages`/`save_messages` (ModelMessagesTypeAdapter JSON, `_MAX_STORED_MESSAGES=1000`) `conversation_store.py:140-159`.
* **RAG bridge** `backend/app/services/rag.py:320-334` `answer_question(question, session_id)` streams then returns `ChatResponse(answer, session_id)`; `_handle_message` calls it with `session_id=sender_id` then truncates 2000 and `send_message`.
* **Frontend integrations** `frontend/src/pages/admin/integrations/index.vue:1-96` `GET /facebook/channels` + create/edit modals with `connectSchema {page_id,page_name,page_token,verify_token,sync_interval}` (`index.vue:32-60`), `UCard` per channel with `Test`/`Sync`/`Edit`/`Delete` (`index.vue:277-388`), `POST /facebook/channels/{id}/sync` and `GET /health`; detail `frontend/src/pages/admin/integrations/[id].vue:52-165` `GET /facebook/channels/{id}` + `GET /health` + `GET /sync-history` + `doSync`/`doTest`.
* **Config** `backend/app/core/config.py:44` `encryption_key: SecretStr | None` used by `encryption.py`; `pyproject.toml:23` already ships `cryptography>=49`.

---

## 2. External / API primary sources — bot.zapps.me/docs (canonical for this task)

> Every claim below cites the exact doc URL + section. `https://developers.zalo.me` (legacy Zalo OA / OpenAPI `openapi.zalo.me`) is **not** the canonical source for the user's bot — it is listed here only where explicitly cross-referenced. Prioritize `bot.zapps.me/docs` when they differ.

### 2.1 Bot types — OA vs Bot (which the user has)

* **Zalo Bot (new platform, user's bot)** — defined at Introduction: "Zalo Bot is an automated account (bot) operating on Zalo Platform, letting businesses/developers interact automatically through messages in the chat window" and supports automation/ERP/CRM hooks. Created via OA **Zalo Bot Manager** → **Zalo Bot Creator** Mini App; name must start with `Bot` prefix (e.g. `Bot MyShop`); Token delivered by Zalo message. Source: `https://bot.zapps.me/docs/` — Introduction section + `https://bot.zapps.me/docs/create-bot/` — Step 1-2.
* **Zalo OA (legacy Official Account)** — **not** what the user has. OA docs live at `https://developers.zalo.me` / `https://openapi.zalo.me`, use `app_id + secret → access_token/refresh_token` OAuth, `Zalo OA Management` portal, message quota/official API. Bot docs never reference `app_id` or OA endpoints; they use `Bot Token` URL form exclusively. See distinction in Terms: bot is managed via `Zalo Bot Creator` and Zalo Platforms agreement, OA is separate product on `zalo.me` ecosystem. Source: `https://bot.zapps.me/docs/create-bot/#bước-1-truy-cập-zalo-oa` (OA lookup is just discovery for Creator), `https://bot.zapps.me/docs/terms/` — Definitions §II.5-6.
* **Capabilities/limits of Bot** — Bot supports: `sendMessage` (text 1-2000 chars, markdown/html + text_styles), `sendPhoto` (`photo` URL + `caption`), `sendSticker` (URL from `stickers.zaloapp.com`), `sendVoice` (`.aac` only, 1-1 only, no groups), `sendChatAction` (`typing`/`upload_photo`), `getMe`, webhook + `getUpdates` (mutually exclusive). Group support is Beta/internal — Bot must be invited via Creator link by group owner; in groups Bot only receives `reply to bot` or `@mention` events, `chat_type=GROUP`. Source: `https://bot.zapps.me/docs/apis/sendMessage/` — Parameters + Rich Text; `https://bot.zapps.me/docs/apis/sendPhoto/`; `https://bot.zapps.me/docs/apis/sendSticker/`; `https://bot.zapps.me/docs/apis/sendVoice/` — 1-1 only limit; `https://bot.zapps.me/docs/apis/sendChatAction/`; `https://bot.zapps.me/docs/webhook/` — chat_type enum; `https://bot.zapps.me/docs/build-bot-interaction-with-group/` — Beta group flow.

### 2.2 Authentication — Bot Token, no refresh flow

* **Format** `BOT_TOKEN = "12345689:abc-xyz"` (numeric prefix + colon + secret). Shown on every API page's URL example.
  Source: `https://bot.zapps.me/docs/authorize/` — Bot Token section.
* **Where to get it** — Delivered by Zalo message immediately after `Tạo Bot` in **Zalo Bot Creator** (opened via Zalo app → search OA **Zalo Bot Manager** → **Tạo bot**). Source: `https://bot.zapps.me/docs/create-bot/#bước-2-thiết-lập-thông-tin-bot`.
* **Reset** — Re-issue from **Zalo Bot Creator** settings; new token delivered by message; old token invalidated. Source: `https://bot.zapps.me/docs/authorize/#bot-token` — tip box.
* **Lifetime** — "Token này sẽ không hết hạn cho tới khi bạn chủ động reset" (does not expire until you reset). No expiry/refresh endpoint exists — contrast with Facebook long-lived 60-day flow or OA `refresh_token`. Source: `https://bot.zapps.me/docs/authorize/#bot-token`.
* **Usage** — Embedded in URL path, not header: `https://bot-api.zaloplatforms.com/bot${BOT_TOKEN}/<functionName>` (e.g. `/bot123456789:abc123xyz/getMe`). All calls must be HTTPS; `GET` or `POST`; params via query string / `application/json` / `form-urlencoded` / `multipart/form-data` (files). UTF-8. Method names case-sensitive. Source: `https://bot.zapps.me/docs/call-api/#định-dạng-url` + `https://bot.zapps.me/docs/call-api/#cách-truyền-tham-số`.
* **Response envelope** — Every response is `{ ok: boolean, result?: any, description?: string, error_code?: number }`. Source: `https://bot.zapps.me/docs/call-api/#phản-hồi-từ-api`.
* **No OAuth for Bot** — There is no `client_id/secret`, no `oauth/access_token`, no `grant_type=fb_exchange_token` equivalent. The entire `developers.zalo.me` OAuth section (OA login, `code→access_token`) does not apply. If you later add Zalo OA as a second integration, that is a separate build.
* **Health probe** — `POST https://bot-api.zaloplatforms.com/bot${TOKEN}/getMe` returns `{ id, account_name, account_type (BASIC), can_join_groups }`. Use as token health check. Source: `https://bot.zapps.me/docs/apis/getMe/` — Sample response.

### 2.3 Webhook — verification, subscription, callback URL, handling, payloads

| Concern | Zalo Bot | Facebook (reference — `backend/app/api/facebook.py:477-504`) |
|---|---|---|
| Subscription API | `POST /bot${TOKEN}/setWebhook { url: "https://…", secret_token: "8..256 chars" }` — requires public HTTPS URL (rejects `localhost`/`127.0.0.1`/`192.168.x.x`/`10.x.x.x`); use ngrok/Cloudflare Tunnel for local. Server probes your URL immediately and returns `verification: { ok, outcome, status_code, hint }` even on failure — URL still saved. | App dashboard registers `hub.verify_token` + callback; platform does `GET /webhook?hub.mode=subscribe&hub.verify_token=&hub.challenge=` |
| Verification secret | `secret_token` sent back on **every event** as header `X-Bot-Api-Secret-Token`; your server must compare `req.headers["x-bot-api-secret-token"] === WEBHOOK_SECRET_TOKEN` else `403`. | `hub.verify_token` string equality on GET |
| Env to produce Token locally | `POST /getUpdates { timeout? }` — long-polling; **mutually exclusive** with webhook (call `POST /deleteWebhook` first). For local dev only; prod should use webhook. | No polling alternative ships in current Facebook code; external Go repo polls `conversations` |
| Info/test/delete | `POST /getWebhookInfo → { url, updated_at }`, `POST /testWebhook → { ok, result: { ok, outcome, status_code, latency_ms, hint } }`, `POST /deleteWebhook → { url:"", updated_at }`. Rate-limited: `errorCode 426` if `testWebhook` called too often. | No equivalents; health is custom `GET /me` |
| HTTP contract | Zalo → you: `POST https://your-webhookurl.com` `Content-Type: application/json`, body `{ ok: true, result: { event_name, message } }`. You must return `2xx` fast; do async work after. | Facebook → you: `POST /webhook` with `object, entry[].messaging[]` |
| Event names | `message.text.received`, `message.image.received`, `message.sticker.received`, `message.voice.received`, `message.unsupported.received` (sent instead of real content for sensitive-user messages, legal compliance). | `messaging[].message.text`, `attachments`, etc. |
| Unsupported redaction | When sender is in protected class (children, etc.) you get `message.unsupported.received` with no `text` — do not retry for content; respond generically. | No analogue |

Sources: `https://bot.zapps.me/docs/apis/setWebhook/` — Parameters + Sample response (verification) + localhost warning; `https://bot.zapps.me/docs/webhook/` — Headers/sample code/payload (X-Bot-Api-Secret-Token, event_name enum, Sample response with `from{id,display_name,is_bot}, chat{id,chat_type}, text, message_id, date`); `https://bot.zapps.me/docs/apis/getWebhookInfo/`; `https://bot.zapps.me/docs/apis/testWebhook/` — outcome enum + 426 limit; `https://bot.zapps.me/docs/apis/deleteWebhook/`; `https://bot.zapps.me/docs/apis/getUpdates/` — mutual exclusion + 30s default timeout.

**Example webhook payloads (from docs)**

Text (PRIVATE):
```json
{ "ok": true, "result": { "event_name": "message.text.received", "message": { "from": { "id": "6ede9afa66b88fe6d6a9", "display_name": "Ted", "is_bot": false }, "chat": { "id": "6ede9afa66b88fe6d6a9", "chat_type": "PRIVATE" }, "text": "Xin chào", "message_id": "2d758cb5e222177a4e35", "date": 1750316131602 } } }
```
Source: `https://bot.zapps.me/docs/webhook/` — Sample response.

Other events share the same envelope; for `message.image.received` the `message` contains `photo` + `caption`; for `message.voice.received` it contains `voice_url`; for `message.sticker.received` it contains `sticker`/`url`. Source: `https://bot.zapps.me/docs/webhook/#message` — field table; plus `https://bot.zapps.me/docs/build-bot-interaction-with-group/#xử-lý-dữ-liệu-webhook` (chat.id reuse for group reply).

### 2.4 Message APIs — reply vs push, endpoints, permissions, quotas, types, base URLs

* **Base URL + version** — Single host, no version in path: `https://bot-api.zaloplatforms.com/bot${BOT_TOKEN}/<method>`. Contrast Facebook `https://graph.facebook.com/v25.0/...`. Source: `https://bot.zapps.me/docs/call-api/#định-dạng-url`, every `/docs/apis/<method>/` page's **URL** line.
* **Reply vs push distinction** — Bot API does **not** separate "reply" vs "push" permission scopes. Any `chat_id` seen from a webhook event (or known `chat.id`) can be messaged via `sendMessage`/`sendPhoto`/… at any time — no 24-hour window or `RESPONSE` tag as with Facebook Messenger. Outbound `chat_id` is the `chat.id` (for PRIVATE equals `from.id`; for GROUP equals the group id). Source: `https://bot.zapps.me/docs/apis/sendMessage/#parameters` (`chat_id` = receiver or conversation id), `https://bot.zapps.me/docs/build-bot-interaction-with-group/#xử-lý-dữ-liệu-webhook` (use `chat.id` to reply to groups).
* **Endpoints & methods**

| Method | URL | Required | Notes |
|---|---|---|---|
| `sendMessage` | `POST /bot${TOKEN}/sendMessage` | `chat_id`, `text(1..2000)` | `parse_mode="markdown"|"html"` or `text_styles[{start,len,st[]}]` — `parse_mode` wins if both sent; offset in UTF-16. |
| `sendPhoto` | `POST /bot${TOKEN}/sendPhoto` | `chat_id`, `photo` (URL/path) | optional `caption(1..2000)` |
| `sendSticker` | `POST /bot${TOKEN}/sendSticker` | `chat_id`, `sticker` (from `stickers.zaloapp.com`) | video guide linked |
| `sendVoice` | `POST /bot${TOKEN}/sendVoice` | `chat_id`, `voice_url` (`.aac` only) | **PRIVATE only** — group `chat_id` may return `ok:true` but not deliver |
| `sendChatAction` | `POST /bot${TOKEN}/sendChatAction` | `chat_id`, `action="typing"|"upload_photo(soon)"` | show typing indicator |
| `getMe` / `getUpdates` / `setWebhook` / `getWebhookInfo` / `testWebhook` / `deleteWebhook` | as above | — | — |

Sources: `https://bot.zapps.me/docs/apis/sendMessage/` — URL/Parameters/Rich Text tables; `https://bot.zapps.me/docs/apis/sendPhoto/`; `https://bot.zapps.me/docs/apis/sendSticker/`; `https://bot.zapps.me/docs/apis/sendVoice/` — 1-1 limit + `.aac` note; `https://bot.zapps.me/docs/apis/sendChatAction/` — action enum.

* **Text length** — `1..2000` chars enforced server-side for `text`/`caption`. Truncate before send (mirror Facebook `reply_text[:1997]+"..."` at `facebook.py:568`). Source: `https://bot.zapps.me/docs/apis/sendMessage/#parameters`.
* **Rich text** — Two modes: `parse_mode markdown` (`**bold**`, `*italic*`, `# heading`, `- list`, `> quote`, `{red}{/red}` color) or explicit `text_styles` (`{start,len,st:["b","c_db342e",...]}` with `f_13|f_15|f_18|f_20` sizes). Cannot combine. Source: `https://bot.zapps.me/docs/apis/sendMessage/#định-dạng-văn-bản-rich-text`.
* **Quota / limits** — Public docs do **not** publish a numeric per-day message cap like OA's "5 messages" rule. Error code for overuse is `429 Quota exceeded`. Subscription tiers (Free vs Premium) change quota; details on `https://bot.zapps.me` pricing page and in Terms §III.4 (subscription plan, auto-renewal). For planning, assume per-bot rate limiting at `429` with `description` + retry semantics; do not hard-code OA quotas onto Bot. Source: `https://bot.zapps.me/docs/error-code/` — `429 Quota exceeded`; `https://bot.zapps.me/docs/terms/#iii-điều-khoản-sử-dụng` — §III.4 Payment; pricing on site navigation (Giá gói).
* **Error codes** — `400 Bad request`, `401 Unauthorized (token expired/invalid)`, `403 Internal server error` (mislabeled), `404 Not found`, `408 Request timeout`, `429 Quota exceeded`. See `error_code` vs `errorCode` variance in `testWebhook` 426 case. Source: `https://bot.zapps.me/docs/error-code/`, `https://bot.zapps.me/docs/apis/testWebhook/#result` (426 on rate-limit).
* **No conversation-list API** — Bot docs expose no `GET /conversations` or `FetchMessages` equivalent. Facebook backfill pattern (`GET /{page_id}/conversations` cursor) has **no Zalo Bot analogue** — history is webhook-or-`getUpdates` only. Do not plan a paginated sync for Zalo Bot; sync button should be no-op or re-verify webhook.

### 2.5 Comparison to legacy Zalo OA (if someone confuses them)

| | Zalo Bot (`bot.zapps.me` / `bot-api.zaloplatforms.com`) — **your case** | Zalo OA (`developers.zalo.me` / `openapi.zalo.me`) |
|---|---|---|
| Auth | `Bot Token` in URL, never expires until reset | `app_id + secret → access_token (short) + refresh_token`, refresh flow |
| Base URL | `https://bot-api.zaloplatforms.com/bot${TOKEN}/method` | `https://openapi.zalo.me/v3.0/...` |
| Webhook auth | `X-Bot-Api-Secret-Token` header | OA webhook `mac` / OA `verify_token` |
| Message send | `sendMessage {chat_id, text}` | `POST /v3.0/oa/message/cs?access_token=` with `recipient.user_id` |
| Quota doc | `429` unspecified, tiered by subscription | Published per-OA quotas (e.g. follower-initiated 5 messages etc.) |
| Docs | `bot.zapps.me/docs/*` | `developers.zalo.me/docs/*` |

If the project later adds OA, it is a second channel type with separate token storage and APIs.

---

## 3. What to add (ponytail minimal) — align to Facebook shape

### 3.1 Backend — 3 endpoints + 1 service + 1 model, reuse existing seams

**New model `zalo_channels` (mirror `facebook_channels`)**
```py
# backend/app/models/zalo_channel.py  ← copy facebook_channel.py:21-35
class ZaloChannelModel(Base):
    __tablename__ = "zalo_channels"
    id: Mapped[str] = Column(String, primary_key=True)          # uuid
    bot_id: Mapped[str] = Column(String, unique=True)           # from getMe.id
    bot_username: Mapped[str] = Column(String, default="")      # account_name e.g. bot.VDKyGxQvc
    bot_token: Mapped[str] = Column(String, default="")         # encrypted via encrypt_token
    verify_token: Mapped[str] = Column(String, default="")      # secret_token for webhook (8..256)
    webhook_url: Mapped[str] = Column(String, default="")       # public https url registered via setWebhook
    last_sync_status: Mapped[str|None] = Column(String, nullable=True)
    last_sync_at: Mapped[str|None] = Column(String, nullable=True)
    created_at: Mapped[datetime|None] = Column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = Column(Boolean, default=True)
    slug: Mapped[str] = Column(String, unique=True, nullable=True, index=True)
```
`bot_token` encrypted at rest via `app/services/encryption.py:29` `encrypt_token` (same `ENCRYPTION_KEY` as Facebook) — decrypt only in `send_message`/`health_check`.

**New service `backend/app/services/zalo_channels.py`** — copy `facebook_channels.py:54-232` with `bot_id` unique check and `bot_token` encrypt/decrypt; same `slugify`, `_ensure_table`, `_to_dict`, `list/get_by_identifier/create/update/delete/update_last_sync_status`.

**New router `backend/app/api/zalo.py` (prefix `/api/zalo` via `routes.py:24`)**

Reuse `facebook.py` patterns line-for-line, but with Zalo semantics:

* `ZALO_API = "https://bot-api.zaloplatforms.com"` + helper `zalo_url(token, method) = f"{ZALO_API}/bot{token}/{method}"` — every call `POST` with `Content-Type: application/json` and token in path (not query). Source: `https://bot.zapps.me/docs/call-api/#định-dạng-url`.
* `async def zalo_send_message(bot_token, chat_id, text) -> bool` — `POST /bot${token}/sendMessage { chat_id, text }`, truncate `>2000 → text[:1997]+"..."`, handle `429` log, return `ok`. Mirror `facebook.py:55-68` but without `page_id` in path or `access_token` param.
* `async def zalo_send_chat_action(bot_token, chat_id)` — `POST /sendChatAction { chat_id, action:"typing" }` before `answer_question`, mirror `facebook.py:81-88` `typing_on`. Source: `https://bot.zapps.me/docs/apis/sendChatAction/`.
* `async def _health_check(bot_token) -> dict` — `POST /bot${token}/getMe`, return `{ ok, bot_id, account_name, account_type, can_join_groups }` or `{ ok:false, error }` on `401/400`. Mirror `facebook.py:94-120`. Source: `https://bot.zapps.me/docs/apis/getMe/`.
* `POST /zalo/webhook` — **not** `GET hub.challenge`. Check `request.headers.get("x-bot-api-secret-token")` against stored `verify_token` (any channel's `verify_token` — like `facebook.py:485` multi-token check); if mismatch → `403`. Parse body `{"ok": true, "result": { "event_name", "message": { "from","chat","text","photo","caption","message_id","date" } } }`; handle `message.text.received` immediately (extract `text`, `chat.id` as session key, `from.display_name` as username), `message.image.received` → use `caption` as text fallback, `message.unsupported.received` → skip/ack; `asyncio.create_task(_handle_message(chat_id, text, from_id, display_name))` mirroring `facebook.py:545`. Always `200`. Source: `https://bot.zapps.me/docs/webhook/` — Headers + Sample code + Parameters/Result tables.
* `async def _handle_message(chat_id, text, from_id, display_name)` — `await zalo_send_chat_action(token, chat_id)`, `response = await answer_question(text, session_id=chat_id)` (not `sender_id` alone — `chat.id` groups map 1-1 for PRIVATE but is group id for GROUP; using `chat.id` keeps GROUP threading correct per `build-bot-interaction-with-group`). `await link_zalo_to_session(chat_id, bot_id, username=display_name)` then `await zalo_send_message(token, chat_id, reply_text)`. Mirror `facebook.py:553-580`.
* `GET /zalo/channels` / `POST /zalo/channels` / `GET /zalo/channels/{id}` / `PUT /zalo/channels/{id}` / `DELETE /zalo/channels/{id}` — same shape as `facebook.py:270-366` but request body `{ bot_token, verify_token, webhook_url?, bot_username? }` (no `page_id/page_name`). `POST` validates `bot_token` via `getMe` before save; on success optionally registers webhook: `POST /bot${token}/setWebhook { url: webhook_url or settings.public_base_url + "/api/zalo/webhook", secret_token: verify_token }` and stores `verification` outcome. Source: `https://bot.zapps.me/docs/apis/setWebhook/` — Parameters + Sample response.
* `GET /zalo/channels/{id}/health` — probe `getMe` as above.
* `POST /zalo/channels/{id}/sync` — for Bot there is no conversation-list backfill; implement as health re-check + `add_sync_log(... "Zalo Bot has no history API — live messages only")` and `update_last_sync_status`. Keep endpoint so UI's `Sync` button doesn't 404.

**Conversation store reuse**
Smallest diff: add two sibling tables (not a migration of facebook ones):

```sql
CREATE TABLE IF NOT EXISTS zalo_conversation_links (
  session_id TEXT PRIMARY KEY, bot_id TEXT NOT NULL, username TEXT, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS zalo_sync_logs (
  id TEXT PRIMARY KEY, bot_id TEXT NOT NULL, status TEXT NOT NULL, detail TEXT, error_message TEXT, created_at TEXT NOT NULL
);
```

Helper fns `link_zalo_to_session` / `list_sessions_with_meta_zalo` / `count_sessions_by_bot` mirror `conversation_store.py:50-98` with `zalo_*` table names. The `conversations` table (`conversations.db: conversations/session_id/messages`) is **shared** — both channels write `ModelRequest`/`ModelResponse` via `save_messages` (already provider-agnostic).

Alternative if you prefer zero new tables: add `channel_type TEXT` to `facebook_conversation_links` — but the ponytail minimal is two new tables (no ALTER of live table).

**Config**
Add `zalo_bot_token: SecretStr | None = None` and `public_base_url: str|None = None` to `backend/app/core/config.py:9-54` only if you want server-side `setWebhook` convenience; otherwise UI can collect `webhook_url` per channel. Keep `encryption_key` reuse.

Wire in `backend/app/api/routes.py:24` — `router.include_router(zalo.router, prefix="/zalo", tags=["zalo"])`.

### 3.2 Frontend — clone Facebook UI, second card type

Reuse `frontend/src/pages/admin/integrations/index.vue:32-60` form pattern:

* `zaloConnectSchema = z.object({ bot_token: z.string().min(1), verify_token: z.string().min(8), webhook_url: z.string().url().optional(), bot_username: z.string().optional() })`
* `GET /zalo/channels` list with same `UCard` grid (`i-lucide-bot` icon vs `i-lucide-facebook`), showing `bot_username`/`bot_id`/`is_active`/`last_sync_status`; actions `Test` (`GET /zalo/channels/{id}/health`) / `Sync` (no-op) / `Edit` / `Delete`.
* Detail page `frontend/src/pages/admin/integrations/[id].vue` clone with `GET /zalo/channels/{id}/sync-history` and a "Webhook URL" copyable field (`/api/zalo/webhook`) + `verify_token` masked.
* Tabs on `index.vue` header: `UTabs [Facebook | Zalo]` — `zalo` tab disabled until wired.

Do **not** expose `bot_token` back from GET — return `has_token: bool` like `facebook.py:244-258` `has_token=bool(ch.get("page_token"))`.

### 3.3 What NOT to add (skipped, add when proven needed)

* OAuth / `fb_exchange_token` equivalent — Zalo Bot has no OAuth; skip. Add when OA is requested.
* Paginated sync (`FetchRecentConversations`/`FetchMessages`) — no Bot API for it; skipping avoids wasted `GET /conversations` that will 404. Add only if Zalo adds a history endpoint.
* Polling loop (`getUpdates` scheduler) — skip; webhook is correct for prod. Keep `getUpdates` as a manual local-dev helper (`POST /zalo/channels/{id}/poll-once`) only if webhook debugging needs it.
* `sendPhoto`/`sendVoice`/`sendSticker` UI — skip; `sendMessage` covers RAG answers. Wire attachment table from `conversation_store` only if attachments become needed.

---

## 4. Feature vs UI split

| Thing | Feature (borrow from Facebook / build) | UI (new, from @nuxt/ui) |
|---|---|---|
| Encrypted `bot_token` at rest | yes — reuse `services/encryption.py:29-51` | no |
| `GET /health` via `getMe` | yes — mirror `facebook.py:94-120` | no — badge/toast only |
| `POST /webhook` header check + async `answer_question` | yes — mirror `facebook.py:507-580` but `X-Bot-Api-Secret-Token` | no |
| `POST /zalo/channels` with `setWebhook` registration | yes — new, no Facebook analogue | `Connect Zalo Bot` modal |
| Sync backfill | no — Zalo Bot has no history API | `Sync` button is health re-check |
| `UTabs` Zalo tab / `UCard` grid | no — that's UI | yes — `@nuxt/ui` `UDashboardPanel` copy |

---

## 5. UI sketch (not copied)

`@nuxt/ui v4` (`frontend/package.json:14`) — keep `UDashboardPanel` header `Integrations` (`index.vue:234-249`). Body becomes `UTabs` with items `Facebook` (`i-lucide-facebook`) and `Zalo` (`i-lucide-bot`). Zalo tab when empty: `UAlert` 3-step `USteps`: 1) Open Zalo → search OA `Zalo Bot Manager` → `Tạo bot` (link `https://zalo.me/app/link/zapps/3082563950095582238/`), 2) Copy `Bot Token` from Zalo message, 3) Paste `Bot Token` + choose `Verify Token` (8..256 chars) + `Webhook URL` (auto `https://{host}/api/zalo/webhook` or ngrok for local) → `Connect`. When connected: stats grid `bot_username | bot_id | has_token | verify_token masked | webhook_url | last webhook at` + actions `Test connection | Edit (UDrawer) | Delete | Copy webhook`. Diagnostics timeline reuses `zalo_sync_logs`.

---

## 6. Verification

Backend lint/check:
```bash
ruff check backend/app/api/zalo.py backend/app/services/zalo_channels.py
pytest -q
```

Manual E2E (repeat for each step, observing logs):

1. **Webhook challenge — not applicable** — Zalo Bot has no GET challenge; instead register via `POST https://bot-api.zaloplatforms.com/bot${TOKEN}/setWebhook {"url":"https://<public>/api/zalo/webhook","secret_token":"<verify_token>"}` → response `verification.ok` should be `true` (`webhook.ok`) or diagnose via `testWebhook` outcome. Source: `https://bot.zapps.me/docs/apis/setWebhook/#sample-response`.
2. **Health** `GET /api/zalo/channels/{id}/health` → `{"ok":true,"account_name":"bot.…","id":"…"} ` with good token, `{"ok":false,"error":"… 401"}` with bad. Mirrors `facebook.py:369-378` contract.
3. **Receive** Send a text to the bot in Zalo → `POST /api/zalo/webhook` header `X-Bot-Api-Secret-Token` matches → log `Zalo message from <display_name> (<chat_id>)` + `answer_question` log.
4. **Reply** `POST /bot${TOKEN}/sendMessage {"chat_id":"<same chat.id>","text":"…"} ` → Zalo shows bot reply; check `result.message_id` returned. Source: `https://bot.zapps.me/docs/apis/sendMessage/#sample-response`.
5. **Limits** Trigger `429` by burst — response body `{"ok":false,"error_code":429,"description":"Quota exceeded"}`; UI should surface `description`. Source: `https://bot.zapps.me/docs/error-code/` + `https://bot.zapps.me/docs/call-api/#phản-hồi-từ-api`.
6. **Group (optional beta)** Invite bot via Creator link `https://zalo.me/app/link/zapps/3082563950095582238/` per `build-bot-interaction-with-group` Steps 2-3; `@mention` the bot or reply to its message → webhook arrives with `chat.chat_type=GROUP` and same `chat.id` used for reply; `sendVoice` with group `chat_id` should be avoided (silent drop). Source: `https://bot.zapps.me/docs/build-bot-interaction-with-group/#bước-2-thêm-bot-vào-nhóm-chat`.
7. **Local fallback** If webhook can't be reached, `POST /bot${TOKEN}/deleteWebhook` then `POST /bot${TOKEN}/getUpdates` should return queued events; re-register webhook for prod. Source: `https://bot.zapps.me/docs/apis/getUpdates/` — mutual exclusion note.

Diagnostics:
```bash
curl -X POST "https://bot-api.zaloplatforms.com/bot${TOKEN}/getMe" | jq
curl -X POST "https://bot-api.zaloplatforms.com/bot${TOKEN}/getWebhookInfo" | jq
curl -X POST "https://bot-api.zaloplatforms.com/bot${TOKEN}/testWebhook" | jq '.result | {ok,outcome,hint,status_code}'
```

---

## Sources — primary only (≥15 bot.zapps.me citations + codebase file:line)

**Official docs — Zalo Bot Platform (`bot.zapps.me/docs`, canonical)**

1. `https://bot.zapps.me/docs/` — Introduction — "Zalo Bot is an automated account… automation/ERP/CRM"
2. `https://bot.zapps.me/docs/create-bot/` — Tạo Bot — Steps 1-2 (Zalo Bot Manager OA → Zalo Bot Creator, name prefix `Bot`, Token by Zalo message); Step 3 (Polling vs Webhook)
3. `https://bot.zapps.me/docs/authorize/` — Xác thực — Bot Token section — format `12345689:abc-xyz`, URL `https://bot-api.zaloplatforms.com/bot${BOT_TOKEN}/functionName`, "không hết hạn… reset", reset via Creator
4. `https://bot.zapps.me/docs/call-api/` — Sử dụng API — Định dạng URL (HTTPS required, URL form), Methods GET/POST, param encodings (query/json/form/multipart), response envelope `{ok,result,description,error_code}`, UTF-8, case-sensitive
5. `https://bot.zapps.me/docs/apis/getMe/` — getMe — `POST …/getMe`, no params, sample `{id,account_name,account_type:BASIC,can_join_groups}`
6. `https://bot.zapps.me/docs/apis/getUpdates/` — getUpdates — long polling, mutually exclusive with webhook, `timeout` param default 30s, "30s" note, deleteWebhook first
7. `https://bot.zapps.me/docs/apis/setWebhook/` — setWebhook — `POST …/setWebhook`, requires public HTTPS (rejects localhost/192.168/10.x), params `url`+`secret_token(8..256)`, immediate `verification{ok,outcome,status_code,hint}`, URL saved even on verification failure
8. `https://bot.zapps.me/docs/apis/testWebhook/` — testWebhook — diagnose without support, sample `webhook.ok` vs `webhook.http.403`, `result.ok` vs outer `ok`, outcome enum (`webhook.ok|http.403|http.404|http.5xx|err.tls|err.dns|err.timeout|err.blocked…`), 426 daily limit
9. `https://bot.zapps.me/docs/apis/deleteWebhook/` — deleteWebhook — removes config to re-enable getUpdates, returns `{url:"",updated_at}`
10. `https://bot.zapps.me/docs/apis/getWebhookInfo/` — getWebhookInfo — `POST …/getWebhookInfo`, returns `{url,updated_at}`
11. `https://bot.zapps.me/docs/webhook/` — Webhook — inbound `POST` to your URL, header `X-Bot-Api-Secret-Token`, HTTPS tip, sample code (header check → 403 else success), Parameters (`ok:true`, `result{event_name,message}`), Result enum (`message.text|image|sticker|voice|unsupported.received`), Message fields (`from{id,display_name,is_bot}, chat{id,chat_type PRIVATE|GROUP}, text, photo, caption, sticker, url, voice_url, message_id, date`), `message.unsupported.received` legal redaction note, Sample PRIVATE payload with `from/display_name`
12. `https://bot.zapps.me/docs/apis/sendMessage/` — sendMessage — `POST …/sendMessage`, `chat_id`+`text(1..2000)` required, `parse_mode markdown|html` vs `text_styles[{start,len,st}]` precedence, markdown syntax table (`**bold**`, `# heading`, `{red}` colors, etc.), HTML tag allowlist, `st` codes (`b,i,u,s,f_13..f_20,c_…`), sample `{message_id,date}` response
13. `https://bot.zapps.me/docs/apis/sendPhoto/` — sendPhoto — `POST …/sendPhoto`, `chat_id`+`photo` required, `caption(1..2000)` optional
14. `https://bot.zapps.me/docs/apis/sendSticker/` — sendSticker — `POST …/sendSticker`, `chat_id`+`sticker` from `stickers.zaloapp.com`
15. `https://bot.zapps.me/docs/apis/sendVoice/` — sendVoice — `POST …/sendVoice`, `chat_id`+`voice_url(.aac)` required, PRIVATE only, group `chat_id` silently undelivered
16. `https://bot.zapps.me/docs/apis/sendChatAction/` — sendChatAction — `POST …/sendChatAction`, `chat_id`+`action=typing|upload_photo(soon)`, sample `{"ok":true}`
17. `https://bot.zapps.me/docs/error-code/` — Bảng mã lỗi — `400 Bad request`, `401 Unauthorized`, `403 Internal server error`, `404 Not found`, `408 Request timeout`, `429 Quota exceeded` + description field note
18. `https://bot.zapps.me/docs/terms/` — Điều khoản — Definitions §II.5-6 (Bot vs Platform), §III.4 subscription tiers (Free vs Premium, auto-renewal), data processing DPA ref — for quota/pricing context
19. `https://bot.zapps.me/docs/build-your-bot/` (+ `https://bot.zapps.me/docs/build-your-bot-with-webhook/`) — Polling vs Webhook tutorials — polling SDK refs (`python-zalo-bot`, `node-zalo-bot`), ngrok/Render/Railway for HTTPS, link `https://zalo.me/app/link/zapps/3082563950095582238/` for Creator
20. `https://bot.zapps.me/docs/build-bot-interaction-with-group/` — Group Beta — Beta notice, invite flow (Creator link → group → Confirm), `@mention` or `reply` triggers, use `chat.id` for group reply, reuse `/docs/webhook/#sample-response` shape

**Codebase — file:line**

* `backend/app/api/facebook.py:36` — `FB_GRAPH_API`, `facebook.py:41-44` — `_get_client`, `facebook.py:55-68` — `send_message`, `facebook.py:71-88` — `mark_seen/typing_on`, `facebook.py:94-120` — `_health_check`, `facebook.py:123-210` — `_sync_fetch_conversations`, `facebook.py:270-366` — CRUD, `facebook.py:369-408` — health+sync, `facebook.py:410-458` — conversations+sync-history, `facebook.py:466-504` — `webhook/info`+`GET /webhook`, `facebook.py:507-580` — `POST /webhook` + `_handle_message`
* `backend/app/services/facebook_channels.py:22-52` — table ensure, `facebook_channels.py:54-116` — helpers, `facebook_channels.py:119-160` — create, `facebook_channels.py:163-232` — update/delete
* `backend/app/models/facebook_channel.py:21-35` — `FacebookChannelModel`
* `backend/app/services/encryption.py:12-51` — `_get_fernet`/`encrypt_token`/`decrypt_token`
* `backend/app/db/conversation_store.py:20-46` — DB open + tables, `conversation_store.py:50-130` — link/sync logs, `conversation_store.py:140-159` — `load/save_messages`
* `backend/app/core/config.py:44` — `encryption_key`, `config.py:9-54` — Settings
* `backend/app/api/routes.py:24` — `facebook.router` mount
* `backend/app/services/rag.py:320-334` — `answer_question`, `rag.py:71-109` — `get_messages`
* `frontend/src/pages/admin/integrations/index.vue:1-96` — load+schemas, `index.vue:277-388` — cards, `index.vue:393-494` — Connect modal
* `frontend/src/pages/admin/integrations/[id].vue:52-165` — health+sync, `[id].vue:211-526` — detail template
* `docs/research/integrations-facebook-feature.md:14-18` — convention reference
