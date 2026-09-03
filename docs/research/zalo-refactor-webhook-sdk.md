# Zalo Bot Refactor — Webhook + python-zalo-bot SDK

Date: 2026-09-01
Scope: Refactor `chat-rag-agent` Zalo integration against PRIMARY sources only — `https://bot.zapps.me/docs` (official Bot Platform) + `https://pypi.org/project/python-zalo-bot/` + its linked source (wheel inspect) — compare current raw `httpx` implementation vs SDK, identify ponytail-minimal webhook/send/verify/quota/frontend fixes.

## Summary

Current `backend/app/api/zalo.py` already implements the **correct** Zalo Bot webhook contract (`X-Bot-Api-Secret-Token` header, `POST /webhook` with `{ok,result{event_name,message}}`), `Bot Token` in URL path `https://bot-api.zaloplatforms.com/bot${TOKEN}/<method>` (no OAuth), `getMe` health, `setWebhook` with `secret_token 8..256`, `sendMessage` 2000-char truncate, `sendChatAction typing`, `429` logging, and async `answer_question` via `chat_id` as `session_id`. The `python-zalo-bot 0.1.9` SDK (pypi `requires_python>=3.8`, `httpx<0.29`, source `zalo_bot/_bot.py:Bot`, `zalo_bot/constants.py:BASE_URL`, `zalo_bot/ext/_application.py:Application`, `zalo_bot/ext/_dispatcher.py:Dispatcher`, `zalo_bot/ext/filters.py:filters.TEXT`) is a thin `python-telegram-bot` port that wraps the **same** REST endpoints but adds `asyncio.run()` sync shims, a wrong `BASE_URL=https://bot-api.zapps.me` (docs expect `bot-api.zaloplatforms.com`), and polling-oriented `Application.run_polling()` — none of which benefit a FastAPI webhook service. Ponytail verdict: **keep raw `httpx`** (8 endpoints, <20 lines each), do not add `python-zalo-bot` dependency. Minimal refactor is 3 fixes: (1) make `webhook_url` optional — don`t 400 on `localhost`/unverified, store channel + return `warning` (2) fix verification ordering / double-check (`secret` before `await request.json()`, single channel match) (3) frontend `webhook_url` empty-allowed + ngrok hint + `testWebhook`/`getWebhookInfo` diagnostics. SDK reuse only for local `getUpdates` polling script, not FastAPI.

---

## 1. Current codebase — primary sources (file:line)

### Routing
* `backend/app/api/routes.py:24-25` — `router.include_router(zalo.router, prefix="/zalo", tags=["zalo"])` mounted at `/api/zalo` alongside `/api/facebook`. Correct prefix, no extra version segment. Source: `backend/app/api/routes.py:25`.
* `backend/pyproject.toml:8-9,22` — already ships `httpx>=0.28.0` and `cryptography>=49.0.0`; adding `python-zalo-bot` (`httpx<0.29,>=0.27` per pypi `requires_dist`) would duplicate `httpx` and add `httpcore` dep for Python 3.14 only. No need to add new dep. Source: `backend/pyproject.toml:9`.

### Backend API — `backend/app/api/zalo.py` (352 lines)
* `ZALO_API="https://bot-api.zaloplatforms.com"` `zalo.py:25` + `_zalo_url(token,method)=f"{ZALO_API}/bot{token}/{method}"` `zalo.py:37-38` — **matches** `https://bot.zapps.me/docs/call-api/#dinh-dang-url` `https://bot-api.zaloplatforms.com/bot${BOT_TOKEN}/functionName` (HTTPS required, token in path, case-sensitive). SDK instead uses `BASE_URL="https://bot-api.zapps.me"` `zalo_bot/constants.py:13` — **mismatched host**. Source: `backend/app/api/zalo.py:25` vs wheel `zalo_bot/constants.py:13`.
* `_get_client()` `zalo.py:30-34` `AsyncClient(timeout=30)` singleton — mirrors `facebook.py:41-44` pattern. SDK uses `HTTPXRequest(connection_pool_size=10, read_timeout=5, write_timeout=5, connect_timeout=5)` `zalo_bot/request/_httpx_request.py:66-77,118-136` — same lib but heavier pooling; not needed for webhook.
* `_zalo_get_me` `zalo.py:41-50` `POST .../getMe` -> `{ok:True,result:{id,account_name}}` else `{ok:False,error:description}` — aligns with `https://bot.zapps.me/docs/apis/getMe/` — Parameters: none; Sample response `{id,account_name,account_type:BASIC,can_join_groups}`. SDK equivalent `Bot.get_me()` `zalo_bot/_bot.py:88-109` `await self._post("getMe")` -> `User.de_json(result,self)` same endpoint, no added value. Source: `backend/app/api/zalo.py:41-50` + `https://bot.zapps.me/docs/apis/getMe/#sample-response`.
* `_zalo_send_message` `zalo.py:53-68` truncates `>2000 -> text[:1997]+"..."`, handles `error_code==429` log, else error — **correct** per `https://bot.zapps.me/docs/apis/sendMessage/#parameters` `text 1..2000 chars` and `https://bot.zapps.me/docs/error-code/` `429 Quota exceeded`. SDK `Bot.send_message(chat_id,text)` `zalo_bot/_bot.py:335-353` same endpoint, same `chat_id+text`, no 429 handling exposed (caller must catch `ZaloError`). Raw code already better for RAG. Source: `backend/app/api/zalo.py:53-68`.
* `_zalo_send_chat_action` `zalo.py:71-75` `POST .../sendChatAction {chat_id,action:"typing"}` swallowed exception — matches `https://bot.zapps.me/docs/apis/sendChatAction/#parameters` `chat_id true, action=typing|upload_photo(soon)` and Sample response `{"ok":true}`. SDK `Bot.send_chat_action(chat_id,action)` `zalo_bot/_bot.py:376-400` same, but `ChatAction.TYPING` `zalo_bot/constants.py:19-20` constant only adds enum sugar. Raw 1-liner sufficient. Source: `backend/app/api/zalo.py:71-75`.
* `ZaloChannelRequest` `zalo.py:78-83` `{bot_token,verify_token,webhook_url?,bot_username?}` and `ZaloChannelUpdateRequest` `zalo.py:85-91` — `verify_token` enforced `8..256` `zalo.py:143-144` — matches `https://bot.zapps.me/docs/apis/setWebhook/#parameters` `secret_token 8..256 chars, attached as X-Bot-Api-Secret-Token`. Good.
* `POST /channels` `zalo.py:141-164` validates `verify_token`, calls `getMe` before save, then `POST setWebhook {url,secret_token}` and checks `verification.ok` else **400** with `hint/outcome/status_code`. This is the **localhost 400 bug** — docs say `Webhook URL vẫn được lưu dù verification thất bại` `https://bot.zapps.me/docs/apis/setWebhook/#sample-response` note, and warns `localhost,127.0.0.1,192.168.x.x,10.x.x.x sẽ bị từ chối` `https://bot.zapps.me/docs/apis/setWebhook/#canh-bao` — but current code raises 400 and leaves already-created channel in DB (created at `zalo.py:150` before webhook call) with 400 returned to frontend, confusing UX. Should store channel and return `warning` instead of 400 when `verification.ok==false` (ponytail fix). Source: `backend/app/api/zalo.py:150-158` + `https://bot.zapps.me/docs/apis/setWebhook/#sample-response` verification field.
* `PUT /channels/{id}` `zalo.py:174-192` re-calls `setWebhook` if token/url/secret changed — fire-and-forget `except:pass` — should reuse same warning logic, not swallow silently; also needs `GET /getWebhookInfo` sync.
* `GET /channels/{id}/health` `zalo.py:206-211` delegates to `_zalo_get_me` — correct probe per `https://bot.zapps.me/docs/apis/getMe/` no params. SDK `Bot.get_me()` identical.
* `POST /channels/{id}/sync` `zalo.py:214-230` correctly notes `Zalo Bot has no history API — live messages only` — matches docs **no conversation-list API** (there is no `GET /conversations` for Bot; polling vs webhook only). Previous `zalo-integration.md:93` correctly flagged. Facebook `_sync_fetch_conversations` `facebook.py:123-210` has no Zalo analogue; no-op is right. Source: `backend/app/api/zalo.py:219-222` + `https://bot.zapps.me/docs/apis/getUpdates/#parameters` (only polling, no backfill).
* `GET /webhook/info` `zalo.py:267-272` returns static `"/api/zalo/webhook"` + first `verify_token` — should call live `POST .../getWebhookInfo` `https://bot.zapps.me/docs/apis/getWebhookInfo/#sample-response` `{url,updated_at}` instead of cached DB value for accurate diagnostics. SDK `Bot._get_webhook_info_async()` `zalo_bot/_bot.py:396-402` does same.
* `POST /webhook` `zalo.py:274-324` — key handler:
  - Reads `X-Bot-Api-Secret-Token` `zalo.py:276` — matches `https://bot.zapps.me/docs/webhook/#sample-code` `req.headers["x-bot-api-secret-token"] !== WEBHOOK_SECRET_TOKEN => 403` and `https://bot.zapps.me/docs/webhook/` Headers: `X-Bot-Api-Secret-Token`.
  - **Ordering bug**: `await request.json()` `zalo.py:277` before secret check — wastes work and could be abused; swap: check `secret` against `tokens = [c.verify_token for c in channels]` first, return 403 before body parse (or parse after). Also currently loads all channels then checks `secret not in tokens ->403` `zalo.py:290-296` good multi-token, but later re-loops to find `target` where `verify_token==secret` `zalo.py:313-320` — could collapse to single lookup and reject if no `target`.
  - Body parsing handles both `{ok,true,result:{event_name,message}}` and flat `{event_name,message}` fallback `zalo.py:280-285` — good robustness per `https://bot.zapps.me/docs/webhook/#parameters` (`ok:true,result{event_name,message}`) and Sample response `zalo.py` shape.
  - `message.unsupported.received` ack `zalo.py:298-299` — correct per `https://bot.zapps.me/docs/webhook/#message` warning: protected class => `message.unsupported.received`, do not retry.
  - Text fallback `message.text or message.caption or ""` `zalo.py:302` — handles `sendPhoto caption` `https://bot.zapps.me/docs/apis/sendPhoto/#parameters` caption 1..2000, good.
  - `chat_id = chat.id or from.id` `zalo.py:308` — aligns with `https://bot.zapps.me/docs/webhook/#message` `Use chat.id to reply` and `https://bot.zapps.me/docs/build-bot-interaction-with-group/#xu-ly-du-lieu-webhook` `chat.id` is group id for GROUP, private id for PRIVATE. Using `chat.id` keeps GROUP threading correct. Good.
  - Global secret match then per-secret target + `asyncio.create_task(_handle_message(...))` `zalo.py:323` — correct fast 2xx per `https://bot.zapps.me/docs/webhook/` (must return 2xx fast; do async after).
* `_handle_message` `zalo.py:327-351` `sendChatAction -> answer_question(session_id=chat_id) -> link_page_to_session -> send_message` truncated `2000` `zalo.py:336-337` — mirrors `facebook.py:553-580`. Note reuse of `link_page_to_session` (facebook link table) `zalo.py:332` — works but `conversation_store.py` currently only has `facebook_conversation_links` `conversation_store.py:32-40` — should add `zalo_conversation_links` sibling or generalize, but sharing same link table is ponytail minimal for now (single session_id space).
  - `link_page_to_session(chat_id, bot_id, username=display_name)` `zalo.py:339` stores Zalo `bot_id` in `page_id` column — technically conflated; ponytail: keep, document that `facebook_conversation_links.page_id` now holds `bot_id` for Zalo too, or add `zalo_` tables later. No need to split now.

### Channels service/model
* `backend/app/models/zalo_channel.py:12-33` `ZaloChannelModel.__tablename__="zalo_channels"` `(id pk, bot_id unique, bot_username, bot_token encrypted, verify_token, webhook_url, last_sync_status, last_sync_at, created_at, is_active, slug unique indexed)` `zalo_channel.py:20-33` — mirrors `facebook_channel.py:21-35` shape, correct single-table per `zalo-integration.md` proposal. Slug `slugify` `zalo_channel.py:12-17` same helper.
* `backend/app/services/zalo_channels.py:18-47` `_ensure_table` with `checkfirst=True` + `ALTER ADD COLUMN slug` + slug backfill `zalo_channels.py:28-47`; `encrypt_token/decrypt_token` `zalo_channels.py:11,65` reuse `app/services/encryption.py:29-51` Fernet `encryption.py:12-26` — correct `bot_token` at rest, same as `facebook_channels.py:149,70`. `get_channel_by_identifier` tries `id|slug|bot_id` `zalo_channels.py:103-110` — analogous to `facebook_channels.py:109-116` `id|slug|page_id`.
* `backend/app/services/zalo_channels.py:113-148` `create_channel` unique `bot_id` 409, slug dedup loop `zalo_channels.py:125-133`, UUID `str(uuid4())`, `encrypt_token` — follows Facebook service verbatim, good.
* `backend/app/db/conversation_store.py:20-46` `conversations.db` with `_get_conn` `conversation_store.py:20-47`, `link_page_to_session` `conversation_store.py:50-59`, `list_sessions_with_meta` `conversation_store.py:73-87`, `add_sync_log/list_sync_logs` `conversation_store.py:113-130`, `load/save_messages` `conversation_store.py:140-159` with `ModelMessagesTypeAdapter` and `_MAX_STORED_MESSAGES=1000` `conversation_store.py:14` — all correctly reused for Zalo without new tables yet (see split below).

### Frontend — `frontend/src/pages/admin/integrations/index.vue` (747 lines)
* Tabs `UTabs [Facebook|Zalo]` `index.vue:328` with `activeTab ref("facebook")` `index.vue:6` + `loadChannels()` `index.vue:124-133` and `loadZaloChannels()` `index.vue:135-141` both call `GET /zalo/channels` `index.vue:138`.
* `zaloConnectSchema` `index.vue:76-81` `{bot_token min1, bot_username optional, webhook_url url optional or "" literal, verify_token min8 max256}` — **correct** optional webhook per docs localhost warning `https://bot.zapps.me/docs/apis/setWebhook/#canh-bao` — but backend currently 400s if webhook fails, so frontend shows generic `getErrorMessage(err)` `index.vue:221` with `hint` lost behind 400. Should surface `warning` not error.
* `zaloConnectState` `index.vue:83` + modal `index.vue:717-731` `UForm` with fields Bot Token (password) `index.vue:720`, Bot Username `index.vue:721`, Webhook URL `index.vue:722` placeholder `https://example.com/api/zalo/webhook`, Verify Token `index.vue:723` hint `8..256 chars, also as secret_token` — good placeholder, but hint should add `ngrok http 3000` for local per `https://bot.zapps.me/docs/build-your-bot-with-webhook/#buoc-2-thiet-lap-webhook` (Render/Railway/Vercel/ngrok). Currently `UAlert` `index.vue:476` says `Set webhook URL to https://your-host/api/zalo/webhook` — should be auto-filled `window.location.origin + "/api/zalo/webhook"` and note `localhost will not verify — leave empty for local dev, use getUpdates`.
* `handleZaloConnect` `index.vue:216-222` `POST /zalo/channels {bot_token,bot_username,webhook_url,verify_token}` `index.vue:219` — passes `undefined` if empty (correct), but if user pastes `http://localhost:8000/api/zalo/webhook` the backend will `POST setWebhook` and 400 with `outcome=webhook.err.blocked` — frontend should intercept 400, keep channel, show `hint` from `testWebhook` outcome.
* `zaloEditSchema` `index.vue:84-89` `webhook_url string optional` — allows blank to clear; good. `handleZaloSave` `zaloEditTarget` `index.vue:224-230` `PUT /zalo/channels/{id}` `index.vue:227` correctly sends `undefined` for blank token.
* Zalo cards `index.vue:478-492` show `bot_username|bot_id|is_active` `index.vue:481-482`, actions `Test` `index.vue:236-239` `GET /zalo/channels/{id}/health` -> `account_name` toast — correct per `https://bot.zapps.me/docs/apis/getMe/#sample-response`. `Sync` `index.vue:241-245` `POST /zalo/channels/{id}/sync` toast — correctly no-op per no history API.
* Missing diagnostics: no `GET /zalo/channels/{id}/webhook-info` or `testWebhook` button — should add `UButton testWebhook` calling `POST .../testWebhook` outcome table per `https://bot.zapps.me/docs/apis/testWebhook/#outcome` to self-diagnose without support.

---

## 2. External primary sources — bot.zapps.me/docs + pypi python-zalo-bot (canonical)

> Every claim cites exact URL + section. `https://developers.zalo.me` (OA legacy) is **not** canonical — bot.zapps.me is per task.

### 2.1 Official Bot Platform — build-your-bot-with-webhook
* Tutorial flow: Step1 create bot via `https://bot.zapps.me/docs/create-bot/` Step1-2 (Zalo Bot Creator, `Bot` prefix, Token via Zalo message), Step2 setup HTTPS webhook via `setWebhook`, Step3 code with SDK (`python-zalo-bot` pypi, `node-zalo-bot` npm) — via ngrok/Render/Railway/Vercel for public HTTPS. Source: `https://bot.zapps.me/docs/build-your-bot-with-webhook/` — Goal + Step2 ngrok + Step3 SDK links + `https://bot.zapps.me/docs/build-your-bot-with-webhook/#buoc-2-thiet-lap-webhook`.
* Polling alternative `getUpdates` mutual exclusion: `deleteWebhook` before `getUpdates`; `timeout` default 30s; local dev only; prod use webhook. Source: `https://bot.zapps.me/docs/build-your-bot/` — Step3 polling link + `https://bot.zapps.me/docs/apis/getUpdates/#sample-response` mutual exclusion note.
* Latest updates `2026-06-03`/`2026-08-11` per page headers — indicates actively maintained.

### 2.2 Authentication — Bot Token
* Format `12345689:abc-xyz` numeric prefix + colon + secret; delivered via Zalo message after `Tạo Bot` in Zalo Bot Creator (opened via OA `Zalo Bot Manager` → `Tạo bot`); name must start with `Bot`; reset via Creator settings invalidates old. Lifetime `không hết hạn cho tới khi bạn chủ động reset` (no expiry). No OAuth/refresh flow. Source: `https://bot.zapps.me/docs/authorize/#bot-token` — Bot Token section + `https://bot.zapps.me/docs/create-bot/#buoc-2-thiet-lap-thong-tin-bot`.
* Usage: `https://bot-api.zaloplatforms.com/bot${BOT_TOKEN}/functionName` all methods HTTPS, GET or POST, params via query/json/form/multipart, UTF-8, case-sensitive. Source: `https://bot.zapps.me/docs/call-api/#dinh-dang-url` + `#cach-truyen-tham-so` + `#luu-y`.
* Response envelope always `{ok:boolean,result?,description?,error_code?}` — unanimous. Source: `https://bot.zapps.me/docs/call-api/#phan-hoi-tu-api`.
### 2.3 Webhook — verification, subscription, handling, payloads
* `POST /bot${TOKEN}/setWebhook {url:https, secret_token:8..256}` `https://bot.zapps.me/docs/apis/setWebhook/#parameters` — requires public HTTPS; rejects `localhost/127.0.0.1/192.168.x.x/10.x.x.x` with `webhook.err.blocked`; immediate `verification{ok,outcome,status_code,latency_ms,hint}` but URL still saved even on failure `https://bot.zapps.me/docs/apis/setWebhook/#sample-response` note `Webhook URL vẫn được lưu dù verification thất bại`.
* `secret_token` returned as header `X-Bot-Api-Secret-Token` on every event; must compare `req.headers["x-bot-api-secret-token"] === WEBHOOK_SECRET_TOKEN` else 403. Sample code at `https://bot.zapps.me/docs/webhook/#sample-code` shows `if(secretToken !== WEBHOOK_SECRET_TOKEN) return 403`. Source: `https://bot.zapps.me/docs/webhook/` — Headers + Sample code.
* Inbound contract Zalo→you: `POST https://your-webhookurl.com` `Content-Type: application/json` body `{ok:true,result:{event_name,message{from{id,display_name,is_bot},chat{id,chat_type PRIVATE|GROUP},text,photo,caption,sticker,url,voice_url,message_id,date}}}` Must return 2xx fast, async after. Event names `message.text|image|sticker|voice|unsupported.received` Source: `https://bot.zapps.me/docs/webhook/#parameters` + `#result` + `#sample-response` + `#message`.
* Unsupported redaction `message.unsupported.received` for special user groups (children etc.) — no text, legal compliance. Source: `https://bot.zapps.me/docs/webhook/#message` warning box.
* Info/test/delete: `POST /getWebhookInfo ->{url,updated_at}` `https://bot.zapps.me/docs/apis/getWebhookInfo/#sample-response`; `POST /testWebhook ->{ok,result{ok,outcome,status_code,latency_ms,hint}}` `https://bot.zapps.me/docs/apis/testWebhook/#sample-response` with outcome enum `webhook.ok|http.403|404|5xx|http.other|err.tls|dns|timeout|conn|proxy|blocked|other`; limit `errorCode 426` if over daily calls `https://bot.zapps.me/docs/apis/testWebhook/#outcome` warning; `POST /deleteWebhook ->{url:"",updated_at}` `https://bot.zapps.me/docs/apis/deleteWebhook/#sample-response` to re-enable `getUpdates`.
* Mutual exclusion `getUpdates` vs webhook: `getUpdates` will not work if webhook set; call `deleteWebhook` first; only for local dev. Source: `https://bot.zapps.me/docs/apis/getUpdates/#parameters` note.
* Group Beta: bot invited via Creator link `https://zalo.me/app/link/zapps/3082563950095582238/` `https://bot.zapps.me/docs/build-bot-interaction-with-group/#buoc-2-them-bot-vao-nhom-chat` Steps2-3 Confirm; in groups bot only receives `reply to bot` or `@mention`; `chat_type=GROUP`; reply via `chat.id` (group id) `https://bot.zapps.me/docs/build-bot-interaction-with-group/#xu-ly-du-lieu-webhook` note.

### 2.4 Message APIs — send/quotas/types
* Base host no version: `https://bot-api.zaloplatforms.com/bot${TOKEN}/method` `https://bot.zapps.me/docs/call-api/#dinh-dang-url`. SDK wrongly uses `https://bot-api.zapps.me` `zalo_bot/constants.py:13` — will 404 or DNS mismatch.
* No reply vs push distinction (unlike Facebook 24h window): any `chat_id` from webhook (`chat.id` for PRIVATE = `from.id`, for GROUP = group id) can be messaged anytime via `sendMessage` `https://bot.zapps.me/docs/apis/sendMessage/#parameters` `chat_id=receiver or conversation id` + group note `https://bot.zapps.me/docs/build-bot-interaction-with-group/#xu-ly-du-lieu-webhook`.
* Endpoints table: `sendMessage POST .../sendMessage {chat_id,text 1..2000}` parse_mode markdown|html vs text_styles `https://bot.zapps.me/docs/apis/sendMessage/#parameters` + Rich Text markdown `**bold** etc.` and `text_styles[{start,len,st}]` precedence `https://bot.zapps.me/docs/apis/sendMessage/#dinh-dang-van-ban-rich-text`; `sendPhoto POST .../sendPhoto {chat_id,photo,caption 1..2000}` `https://bot.zapps.me/docs/apis/sendPhoto/#parameters`; `sendSticker POST .../sendSticker {chat_id,sticker from stickers.zaloapp.com}` `https://bot.zapps.me/docs/apis/sendSticker/`; `sendVoice POST .../sendVoice {chat_id,voice_url .aac} PRIVATE only` `https://bot.zapps.me/docs/apis/sendVoice/`; `sendChatAction POST .../sendChatAction {chat_id,action=typing|upload_photo(soon)}` `https://bot.zapps.me/docs/apis/sendChatAction/#parameters` action enum.
* Sample responses: `sendMessage` -> `{message_id,date}` `https://bot.zapps.me/docs/apis/sendMessage/#sample-response`; `sendChatAction` -> `{"ok":true}` `https://bot.zapps.me/docs/apis/sendChatAction/#sample-response`; `getMe` -> `{id,account_name,account_type:BASIC,can_join_groups}` `https://bot.zapps.me/docs/apis/getMe/#sample-response`.
* Quota/limits: no numeric per-day cap published like OA; error `429 Quota exceeded` `https://bot.zapps.me/docs/error-code/` table; plus 400 Bad request, 401 Unauthorized, 403 Internal server error, 404 Not found, 408 Request timeout. Subscription tiers Free vs Premium pricing on site; `testWebhook` 426 limit `https://bot.zapps.me/docs/apis/testWebhook/#outcome` warning.
* No conversation-list/backfill API — webhook or `getUpdates` only `https://bot.zapps.me/docs/apis/getUpdates/#sample-response` reference.

### 2.5 pypi python-zalo-bot — source inspect (wheel 0.1.9)
* Pypi meta: `name python-zalo-bot 0.1.9` `version 0.1.9 2026-01-27` `requires_python >=3.8` `requires_dist httpx<0.29,>=0.27` + `httpcore>=1.0.9; python>=3.14` `license MIT` `Homepage https://github.com/yourusername/python-zalo-bot` placeholder (no real public repo), description `based on python-telegram-bot MIT` `https://github.com/python-telegram-bot/python-telegram-bot`. Source: `https://pypi.org/project/python-zalo-bot/` — Info + `Invoke-RestMethod https://pypi.org/pypi/python-zalo-bot/json` (wheel SHA `9c...`).
* Wheel inspect `C:\Users\ThongLe\AppData\Local\Temp\opencode\zalo-bot\unzipped\`:
  - `zalo_bot/__init__.py:1-10` exports `Bot,User,constants,error,Message,Chat,Update`.
  - `zalo_bot/_bot.py:31-48` `class Bot(ZaloObject, AsyncContextManager)` `__init__(token, base_url=BASE_URL)` `self._base_url=f"{base_url}/bot{token}"` + `self._request=(HTTPXRequest(),HTTPXRequest())` tuple for `getUpdates` vs others — mirrors PTB double-client for polling but irrelevant for webhook.
  - `zalo_bot/_bot.py:88-109` `async get_me() -> User` `await self._post("getMe")` + `User.de_json`.
  - `zalo_bot/_bot.py:111-165` `async get_update(timeout,offset,limit)` notes `will not work if webhook set` + `await self._post("getUpdates", timeout)` + parse `Update.de_json`.
  - `zalo_bot/_bot.py:196-246` `_post/_do_post` `RequestData+RequestParameter` -> `request.post(url=f"{base_url}/{endpoint}")` dropping None — same as raw `httpx.AsyncClient.post`.
  - `zalo_bot/_bot.py:248-294` `initialize()` `await gather(request.initialize)` + `await get_me()` token validation; `shutdown()` opposite; `__aenter__/__aexit__` pattern — wrong for FastAPI lifespan (would double-init per request).
  - `zalo_bot/_bot.py:307-353` `send_message`, `send_photo`, `send_sticker` → `_send_message(endpoint,data)` -> `Message.de_json` — same endpoints as raw, adds `reply_to_message_id` passthrough not in docs (will be ignored).
  - `zalo_bot/_bot.py:355-376` `_set_webhook_async` + `set_webhook(url,secret_token)` sync wrapper `asyncio.run(self._set_webhook_async(...))` — **breaks FastAPI** (cannot call `asyncio.run` inside running loop). Same pattern `delete_webhook`, `get_webhook_info`, etc. Source: `zalo_bot/_bot.py:358-403`.
  - `zalo_bot/_bot.py:376-410` `send_chat_action(chat_id,action)` -> `_post("sendChatAction")` bool.
  - `zalo_bot/constants.py:13` `BASE_URL="https://bot-api.zapps.me"` — **wrong host** vs docs `bot-api.zaloplatforms.com` (typo; will fail live).
  - `zalo_bot/_update.py:10-35` `class Update(ZaloObject)` `message:Message` + `effective_user` -> `message.from_user` + `Update.de_json(data)` mapping `message=Message.de_json(data.get("message"))` — but docs envelope is `{ok:true,result:{event_name,message: {...}}}` — SDK expects `data["message"]` at top level, so webhook glue `Update.de_json(request.json()["result"], bot)` `pypi description webhook example` does `Update.de_json(request.get_json()["result"], bot)` correctly unwraps `result`.
  - `zalo_bot/_message.py:1-60` `class Message` `message_id,date,chat,text,from_user,photo_url,sticker` + `Message.de_json` maps `from`->`from_user`, `chat Chat.de_json`, `date fromtimestamp(date/1000)`, `reply_text/reply_photo/reply_sticker/reply_action` via `get_bot().send_*` — correct but assumes `GET` token stored on `ZaloObject.set_bot`.
  - `zalo_bot/_chat.py:6-18` `class Chat id,type` `de_json data["id"],chat_type` — minimal.
  - `zalo_bot/_user.py:12-48` `class User id,display_name,account_name,account_type,is_bot,can_join_groups`.
  - `zalo_bot/_webhook.py:6-18` `class Webhook url,updated_at`.
  - `zalo_bot/ext/_application.py:1-61` `Application(bot, handlers)` `add_handler`, `process_update(update)` iterates handlers `check_update -> handle_update`, `run_polling()` `asyncio.run(_polling_loop)` with `while: get_update(timeout=30)` + sleep1 — polling-only, not for FastAPI.
  - `zalo_bot/ext/_dispatcher.py:1-33` `Dispatcher(bot,update_queue,workers)` `add_handler -> Application.add_handler`, `process_update(update)` sync via `Application.process_update_sync` -> `asyncio.run` again — unsafe in ASGI.
  - `zalo_bot/ext/filters.py:1-22` `BaseFilter` with `& | ~` + `TEXT=BaseFilter(lambda update: bool(message.text))`, `COMMAND=startswith("/")`, `PHOTO,STICKER,ALL` — no `chat_type` filter, no `GROUP` awareness.
  - `zalo_bot/request/_httpx_request.py:66-136` `HTTPXRequest(pool_size=10, read_timeout=5...)` — default timeouts 5s, but webhook example uses no timeout tuning.
  - `zalo_bot/error.py:1-60,92-100` `ZaloError, Forbidden, InvalidToken, NetworkError, BadRequest, RetryAfter(retry_after)` — `RetryAfter` for flood but docs use `429` `error_code`.
* Example snippets from pypi description:
  - Polling `ApplicationBuilder().token("TOKEN").build(); app.add_handler(CommandHandler("start",start)); MessageHandler(filters.TEXT & ~filters.COMMAND,echo); app.run_polling()` — classic PTB pattern, works for local `getUpdates` but not FastAPI.
  - Webhook Flask example `Flask request; bot=Bot(token); bot.set_webhook(url,secret_token) inside app.app_context(); dispatcher=Dispatcher(bot,None,workers=0); dispatcher.add_handler(...); @app.route("/webhook") update=Update.de_json(request.get_json()["result"],bot); dispatcher.process_update(update)` — translates to FastAPI as `update=Update.de_json(body["result"],bot)` + `dispatcher.process_update` but still uses Flask+sync `asyncio.run` anti-pattern.
* Conclusion: SDK is **thin wrapper** over same 8 REST endpoints, adds PTB-style handlers useful for pure polling bots, but for webhook FastAPI the raw `httpx` is shorter, async-native, host-correct, and avoids `asyncio.run` pitfalls. Not worth adding dep for webhook service.

---

## 3. Feature vs SDK split

| Feature | Build yourself (raw httpx) @ `backend/app/api/zalo.py` | Borrow from SDK `python-zalo-bot` | Verdict |
|---|---|---|---|
| Auth `Bot Token` in URL, no OAuth | already done `ZALO_API/bot{token}/method` `zalo.py:37-38` | `Bot.__init__(token)` `zalo_bot/_bot.py:31-48` stores token + base_url | **keep raw** — SDK adds placeholder host mismatch |
| `getMe` health | `_zalo_get_me` `zalo.py:41-50` 9 lines | `Bot.get_me()` `zalo_bot/_bot.py:88-109` | keep raw — same |
| `getUpdates` polling | not needed for webhook prod | `Bot.get_update()` `zalo_bot/_bot.py:111-165` + `Application.run_polling()` `zalo_bot/ext/_application.py:42-61` | **SDK only for local dev script** `scripts/zalo_poll.py` using `Bot+get_update` loop; do not wire into FastAPI |
| `setWebhook/getWebhookInfo/testWebhook/deleteWebhook` | `_zalo_url` + `POST setWebhook` `zalo.py:152-153` + missing `getWebhookInfo/testWebhook` | `Bot.set_webhook/get_webhook_info/delete_webhook` `zalo_bot/_bot.py:355-403` but sync `asyncio.run` | **keep raw**, add `getWebhookInfo`+`testWebhook` raw `httpx` helpers (2 lines each) |
| `sendMessage/sendPhoto/sendChatAction` | `_zalo_send_message/chat_action` `zalo.py:53-75` with 2000 trunc + 429 | `Bot.send_message/send_photo/send_chat_action` `zalo_bot/_bot.py:307-410` | keep raw |
| Webhook header verification | `x-bot-api-secret-token` check `zalo.py:276,294` vs tokens list | no SDK middleware for FastAPI | keep raw, fix ordering |
| Event dispatch `message.text|image|sticker|voice|unsupported` | manual `event_name` if chain `zalo.py:287-304` | `Update.de_json` `zalo_bot/_update.py:25-35` + `Dispatcher.process_update` `zalo_bot/ext/_dispatcher.py:15-18` + `filters.TEXT` `zalo_bot/ext/filters.py:14` + `CommandHandler/MessageHandler` `zalo_bot/ext/_handler.py:11-40` | **keep raw** — SDK dispatch still manual `Update.de_json(body["result"],bot)` and `filters` incomplete (no image caption fallback); raw is 10 lines |
| Quota 429 / error 400/401 | logged `zalo.py:61-64` | `error.py:RetryAfter, BadRequest` exceptions `zalo_bot/error.py:52-95` | keep raw log, optionally raise `HTTPException 429` |
| Conversation store | shared `conversations.db` + `facebook_conversation_links` `conversation_store.py:32-40` | no store — SDK leaves storage to user | keep raw, document conflation |
| Frontend `webhook_url` 400 on localhost | backend 400 if `verification.ok==false` `zalo.py:156-158` | no frontend | **fix raw** — allow empty or blocked URL, store + warn |

---

## 4. What to refactor — ponytail minimal (fewest files, shortest diff)

> Ladder: 1. Need? yes (webhook+quota fixes) 2. Already in codebase? reuse `facebook.py`/`encryption.py` 3. Stdlib? yes 4. Native? HTTPS via FastAPI 5. New dep? no (skip SDK).

### 4.1 Backend — 3 fixes, no new tables

**Fix A — Make `webhook_url` optional, never 400 on localhost (ponytail: 1 file, 15 lines)**
`backend/app/api/zalo.py:141-164` current:
```py
ch = await create_channel(...)
if req.webhook_url:
    resp = await client.post(_zalo_url(..., "setWebhook"), json={"url": url, "secret_token": secret})
    ver = (data.get("result") or {}).get("verification") or {}
    if not ver.get("ok"):
        raise HTTPException(400, hint/outcome)  # <- deletes UX
```
Refactor (keep channel, return warning):
```py
warning = None
if req.webhook_url:
    # ponytail: localhost/ngrok case — Zalo rejects but saves URL; don`t 400 per docs "vẫn được lưu dù verification thất bại"
    try:
        resp = await _get_client().post(_zalo_url(req.bot_token, "setWebhook"), json={"url": req.webhook_url, "secret_token": req.verify_token})
        data = resp.json() if "application/json" in resp.headers.get("content-type","") else {}
        result = data.get("result") or {}
        ver = result.get("verification") or {}
        if not ver.get("ok"):
            warning = ver.get("hint") or ver.get("outcome") or data.get("description") or resp.text[:200]
            logger.warning("setWebhook verification %s: %s", bot_id, warning)
            # outcome webhook.err.blocked -> hint to use ngrok
            if ver.get("outcome") == "webhook.err.blocked":
                warning = "Webhook URL not publicly reachable (localhost/10.x/192.168). Leave blank for local dev or use ngrok: `ngrok http 8000` then setWebhook again. " + warning
        else:
            logger.info("setWebhook %s ok %s", bot_id, ver)
    except Exception as e:
        warning = str(e)[:300]
        logger.warning("setWebhook failed %s: %s", bot_id, warning)
return {**_to_response(ch), "warning": warning}  # 200 with warning, not 400
```
Prevents `400 Bad request` for `http://localhost:8000/api/zalo/webhook` (which Zalo always rejects `https://bot.zapps.me/docs/apis/setWebhook/#canh-bao`). Frontend shows `UAlert warning` instead of error. Same for `PUT` `zalo.py:187-191` — change to warning-log not swallow.

Add validators:
- `webhook_url` if present must be `https://` (Zalo requires HTTPS) unless empty — current `ZaloChannelRequest.webhook_url: str|None` `zalo.py:81` has no URL check; frontend zod does `z.string().url()` `index.vue:79` which allows `http://localhost` but Zalo will block; keep zod but add hint text `must be https public URL; leave empty for local`.
- `verify_token` `8..256` already enforced `zalo.py:143-144` matches `https://bot.zapps.me/docs/apis/setWebhook/#parameters`.

**Fix B — Webhook handler ordering + single lookup + 2 new diag endpoints**
`backend/app/api/zalo.py:274-324` refactor:
```py
@router.post("/webhook")
async def zalo_webhook(request: Request, db: AsyncSession = Depends(get_async_session)):
    # ponytail: check secret before parsing body — FastAPI already parsed? keep but early return 403
    secret = request.headers.get("x-bot-api-secret-token", "")
    # fast path: load tokens once
    channels = await list_channels(db)
    if not channels:
        return Response(status_code=200)  # ack but no config
    tokens = {c["verify_token"]: c for c in channels}  # map
    target = tokens.get(secret)
    if not target:
        logger.warning("Zalo webhook secret mismatch got=%s", secret[:8] if secret else "<empty>")
        return Response(status_code=403)
    body = await request.json()
    logger.info("Zalo webhook %s secret ok", target["bot_id"])
    result = body.get("result") if isinstance(body, dict) else None
    if not result:
        result = body if isinstance(body.get("event_name"), str) else None
    if not result or not isinstance(result, dict):
        return Response(status_code=200)
    event_name = result.get("event_name","")
    if event_name == "message.unsupported.received":
        return Response(status_code=200)
    message = result.get("message",{}) if isinstance(result.get("message"), dict) else {}
    text = message.get("text") or message.get("caption") or ""
    if not text: return Response(status_code=200)
    chat = message.get("chat",{}) if isinstance(message.get("chat"), dict) else {}
    from_user = message.get("from",{}) if isinstance(message.get("from"), dict) else {}
    chat_id = str(chat.get("id") or from_user.get("id") or "")
    if not chat_id: return Response(status_code=200)
    display_name = from_user.get("display_name") or ""
    bot_token = target["bot_token"]
    asyncio.create_task(_handle_message(target["bot_id"], bot_token, chat_id, text, display_name))
    return Response(status_code=200)
```
Add diagnostics (reuse `_zalo_get_me` pattern):
```py
@router.get("/channels/{identifier}/webhook-info")
async def zalo_webhook_info(identifier: str, ...):
    ch = await get_channel_by_identifier(db, identifier)
    # ponytail: live probe, not DB cache
    resp = await _get_client().post(_zalo_url(ch["bot_token"], "getWebhookInfo"))
    return resp.json()  # {ok,result{url,updated_at}} per https://bot.zapps.me/docs/apis/getWebhookInfo/

@router.post("/channels/{identifier}/test-webhook")
async def zalo_test_webhook(identifier: str, ...):
    ch = await get_channel_by_identifier(db, identifier)
    resp = await _get_client().post(_zalo_url(ch["bot_token"], "testWebhook"))
    data = resp.json() if "json" in resp.headers.get("content-type","") else {"ok":False}
    # surface outcome/latency_ms/hint per https://bot.zapps.me/docs/apis/testWebhook/#outcome
    # also handle 426 deleteWebhook rate-limit: data.get("errorCode")==426
    return data
```
Both are 5-line wrappers; match SDK `get_webhook_info` but via raw httpx, no `asyncio.run`.

**Fix C — Keep raw sends, just harden 429 + truncate (already done)**
* `zalo.py:53-68` already correct; add `Retry-After` header parse if 429 returns `retry_after` seconds per SDK `RetryAfter` `zalo_bot/error.py:92-100` — but docs give no seconds, just `429 Quota exceeded` `https://bot.zapps.me/docs/error-code/` so log `description` and return `HTTPException 429` for diagnostics endpoint, not for webhook sends.
* `sendPhoto`/`sendVoice` not needed for RAG ponytail; skip — add later if attachments required.
### 4.2 Conversation store — no schema change
Keep sharing `facebook_conversation_links` / `facebook_sync_logs` via `link_page_to_session` `conversation_store.py:50-59` and `add_sync_log` `conversation_store.py:113-119` — session_id is `chat.id` (PRIVATE) or group id (GROUP) per `https://bot.zapps.me/docs/webhook/#message` `chat.id` reply target. Document in code comment `page_id column holds bot_id for Zalo`. When `zalo_*` tables needed (quota 1k rows), add sibling tables `zalo_conversation_links/session`+`zalo_sync_logs` — zero migration now.

### 4.3 Frontend — 2 lines + hint
`frontend/src/pages/admin/integrations/index.vue`:
* `zaloConnectSchema` `index.vue:76-81` change `webhook_url: z.string().url().optional().or(z.literal(""))` to `.optional().or(z.literal("")).refine(v=>!v || v.startsWith("https://"), "Must be https public URL")` + hint `leave empty for local dev — use ngrok https://.../api/zalo/webhook for prod` per `https://bot.zapps.me/docs/build-your-bot-with-webhook/#buoc-2-thiet-lap-webhook`.
* `handleZaloConnect` `index.vue:216-222` handle warning response: `const {data}=await api.post(...); if(data.warning) toast.add({color:"warning", description:data.warning, title:"Connected with warning"}); else toast success`. Surface `outcome hint` from `webhook.err.blocked` etc. per `https://bot.zapps.me/docs/apis/testWebhook/#outcome` table.
* `UAlert` `index.vue:476` make webhook URL auto `const autoWebhook = window.location.origin + "/api/zalo/webhook"` computed + `UButton copy` + note `localhost will fail verification — testWebhook will show webhook.err.blocked`.
* Add `UButton` per card `Test Webhook` -> `POST /zalo/channels/{id}/test-webhook` -> toast `outcome/hint/latency_ms` per `https://bot.zapps.me/docs/apis/testWebhook/#sample-response` and 426 handling.

### 4.4 What NOT to add (ponytail: skipped, add when proven)
* `python-zalo-bot` dep — skipped: host mismatch `zalo_bot/constants.py:13`, `asyncio.run` inside FastAPI `zalo_bot/_bot.py:358`, polling-only `Application.run_polling()` `zalo_bot/ext/_application.py:56` — would require wrapping ASGI lifespan, adds 60KB wheel for 20 lines of httpx you already have. Add only if you need `filters.COMMAND` routing for >5 commands or `InputFile` uploads beyond `photo` URL.
* OAuth / `fb_exchange_token` equivalent — none per `https://bot.zapps.me/docs/authorize/#bot-token` no OAuth.
* Paginated sync — no Bot `GET /conversations` `https://bot.zapps.me/docs/apis/getUpdates/` only webhook/getUpdates.
* Polling loop in prod — keep webhook; local `getUpdates` script outside FastAPI `python scripts/zalo_poll.py` using `bot.get_update(timeout=30)` is fine.
* `sendPhoto/sendVoice/sendSticker` UI — skip until RAG needs images.
* Separate `zalo_*` SQLite tables — skip until `facebook_conversation_links` row count >1k or group naming collides.

---

## 5. Verification

Backend lint/check:
```bash
ruff check backend/app/api/zalo.py backend/app/services/zalo_channels.py
pytest -q
```
Manual E2E (repeat for each, observing logs):
1. **Connect empty webhook** `POST /api/zalo/channels {"bot_token":"123456:abc","verify_token":"supersecret123","webhook_url":""}` -> `200 {warning:null}` + DB row `zalo.py:148` creates channel. Previously 400 on `http://localhost...` now 200+warning per docs `Web Hook URL vẫn được lưu dù verification thất bại` `https://bot.zapps.me/docs/apis/setWebhook/#sample-response`.
2. **Webhook verification blocked** `POST /api/zalo/channels {"webhook_url":"http://localhost:8000/api/zalo/webhook"}` -> `200 {warning:"webhook.err.blocked ... ngrok http 8000"}` not 400; frontend shows warning toast not error. Verify via `curl -X POST https://bot-api.zaloplatforms.com/bot${TOKEN}/testWebhook | jq ''.result | {outcome,hint,status_code}''` shows `webhook.err.blocked` `https://bot.zapps.me/docs/apis/testWebhook/#outcome`.
3. **Health** `GET /api/zalo/channels/{id}/health` -> `{"ok":true,"bot_id":"1459232241454765289","account_name":"bot.VDKyGxQvc"}` good token, `{"ok":false,"error":"...401"}` bad per `https://bot.zapps.me/docs/error-code/` 401 Unauthorized and `https://bot.zapps.me/docs/apis/getMe/#sample-response`.
4. **Header verification** `curl -X POST http://localhost:8000/api/zalo/webhook -H "X-Bot-Api-Secret-Token: wrong" -d "{\"ok\":true,\"result\":{\"event_name\":\"message.text.received\",\"message\":{\"chat\":{\"id\":\"123\",\"chat_type\":\"PRIVATE\"},\"from\":{\"id\":\"123\",\"display_name\":\"Ted\"},\"text\":\"hi\"}}}"` -> `403` per `https://bot.zapps.me/docs/webhook/#sample-code` secret check; correct token -> `200` then `asyncio.create_task(_handle_message)` log `Processing Zalo message from 123: ''hi''` `zalo.py:329`.
5. **Receive+Reply** Send text to bot in Zalo -> `POST /api/zalo/webhook` header matches -> `sendChatAction typing` `POST .../sendChatAction {chat_id,action:"typing"}` per `https://bot.zapps.me/docs/apis/sendChatAction/#parameters` -> `answer_question(text, session_id=chat_id)` -> `sendMessage {chat_id,text}` per `https://bot.zapps.me/docs/apis/sendMessage/#parameters` trunc 2000 `zalo.py:54-55,336-337`; Zalo shows reply `message_id/date` `https://bot.zapps.me/docs/apis/sendMessage/#sample-response`.
6. **Unsupported** send protected-user message -> `event_name=message.unsupported.received` -> ack 200 no reply per `https://bot.zapps.me/docs/webhook/#message` warning.
7. **Quota 429** burst sends -> `{"ok":false,"error_code":429,"description":"Quota exceeded"}` `https://bot.zapps.me/docs/error-code/` logged `Zalo quota exceeded` `zalo.py:62`; `testWebhook` 426 daily limit returns `ok:false errorCode 426` `https://bot.zapps.me/docs/apis/testWebhook/#outcome` warning.
8. **Diagnostics** `GET /api/zalo/channels/{id}/webhook-info` -> `{url,updated_at}` per `https://bot.zapps.me/docs/apis/getWebhookInfo/#sample-response`; `POST .../test-webhook` -> `{ok:true,result{ok:outcome,latency_ms}}` per `https://bot.zapps.me/docs/apis/testWebhook/#sample-response`.
9. **Local fallback** `POST .../deleteWebhook` -> `{url:"",updated_at}` per `https://bot.zapps.me/docs/apis/deleteWebhook/#sample-response`; then `POST .../getUpdates {timeout:30}` returns queued events per `https://bot.zapps.me/docs/apis/getUpdates/#parameters`.
10. **Group beta (optional)** Invite via `https://zalo.me/app/link/zapps/3082563950095582238/` `https://bot.zapps.me/docs/build-bot-interaction-with-group/#buoc-2-them-bot-vao-nhom-chat` @mention or reply -> webhook `chat.chat_type=GROUP` then reply via `chat.id` `https://bot.zapps.me/docs/build-bot-interaction-with-group/#xu-ly-du-lieu-webhook`; `sendVoice` group silently dropped per docs.

Diagnostics curl:
```bash
curl -X POST "https://bot-api.zaloplatforms.com/bot${TOKEN}/getMe" | jq
curl -X POST "https://bot-api.zaloplatforms.com/bot${TOKEN}/getWebhookInfo" | jq
curl -X POST "https://bot-api.zaloplatforms.com/bot${TOKEN}/testWebhook" | jq ''.result | {ok,outcome,hint,status_code}''
# localhost tunneling
ngrok http 8000
curl -X POST "https://bot-api.zaloplatforms.com/bot${TOKEN}/setWebhook" -H "Content-Type: application/json" -d ''{"url":"https://<ngrok>/api/zalo/webhook","secret_token":"supersecret123"}'' | jq ''.result.verification''
```

---

## Sources — primary only (≥15 bot.zapps.me + pypi + wheel + codebase file:line)

**Official docs — Zalo Bot Platform (`bot.zapps.me/docs`, canonical)**

1. `https://bot.zapps.me/docs/build-your-bot-with-webhook/` — Build with Webhook — Goal + Step2 HTTPS via ngrok/Render/Railway + Step3 SDK links `python-zalo-bot`/`node-zalo-bot`
2. `https://bot.zapps.me/docs/webhook/` — Webhook — inbound POST `https://your-webhookurl.com`, header `X-Bot-Api-Secret-Token`, Sample code 403 else success, Parameters `ok:true result{event_name,message}`, Result enum `message.text|image|sticker|voice|unsupported.received`, Message fields `from{id,display_name,is_bot},chat{id,chat_type PRIVATE|GROUP},text,photo,caption,sticker,url,voice_url,message_id,date`, unsupported redaction warning, Sample PRIVATE payload
3. `https://bot.zapps.me/docs/apis/setWebhook/` — setWebhook — `POST .../setWebhook` public HTTPS only, rejects `localhost/127.0.0.1/192.168/10.x`, params `url+secret_token 8..256`, immediate `verification{ok,outcome,status_code,latency_ms,hint}`, URL saved even on failure
4. `https://bot.zapps.me/docs/apis/testWebhook/` — testWebhook — diagnose `result.ok` vs outer `ok`, outcome enum `webhook.ok|http.403|404|5xx|err.tls|dns|timeout|blocked|other`, latency_ms, hint, 426 daily limit `errorCode 426`
5. `https://bot.zapps.me/docs/apis/getWebhookInfo/` — getWebhookInfo — `POST .../getWebhookInfo` `{url,updated_at}`
6. `https://bot.zapps.me/docs/apis/deleteWebhook/` — deleteWebhook — removes config to re-enable getUpdates `{url:"",updated_at}`
7. `https://bot.zapps.me/docs/apis/getMe/` — getMe — `POST .../getMe` no params, sample `{id,account_name,account_type:BASIC,can_join_groups}`
8. `https://bot.zapps.me/docs/apis/getUpdates/` — getUpdates — long polling mutually exclusive with webhook, `timeout` default 30s, deleteWebhook first, dev only
9. `https://bot.zapps.me/docs/call-api/` — Call API — URL `https://bot-api.zaloplatforms.com/bot${BOT_TOKEN}/functionName`, HTTPS, GET/POST, query/json/form/multipart, envelope `{ok,result,description,error_code}`, UTF-8, case-sensitive
10. `https://bot.zapps.me/docs/authorize/` — Auth — Bot Token `12345689:abc-xyz` no expiry until reset, via Bot Creator, message `không hết hạn... reset`
11. `https://bot.zapps.me/docs/apis/sendMessage/` — sendMessage — `POST .../sendMessage` `chat_id+text 1..2000`, `parse_mode markdown|html` vs `text_styles[{start,len,st}]` precedence, markdown table, HTML allowlist, st codes `b,i,u,s,f_13..f_20,c_...`, sample `{message_id,date}`
12. `https://bot.zapps.me/docs/apis/sendPhoto/` — sendPhoto — `POST .../sendPhoto` `chat_id+photo` required, `caption 1..2000` optional
13. `https://bot.zapps.me/docs/apis/sendChatAction/` — sendChatAction — `POST .../sendChatAction` `chat_id+action=typing|upload_photo(soon)` sample `{"ok":true}`
14. `https://bot.zapps.me/docs/error-code/` — Error code — `400 Bad request`, `401 Unauthorized`, `403 Internal server error`, `404 Not found`, `408 Request timeout`, `429 Quota exceeded`
15. `https://bot.zapps.me/docs/create-bot/` — Create Bot — Step1 OA `Zalo Bot Manager` -> Creator, Step2 name `Bot` prefix, Token via Zalo message, Step3 webhook vs polling via `getUpdates`/`setWebhook`
16. `https://bot.zapps.me/docs/build-bot-interaction-with-group/` — Group Beta — invite via `https://zalo.me/app/link/zapps/3082563950095582238/`, Confirm, `@mention`/`reply` triggers, use `chat.id` group id
17. `https://bot.zapps.me/docs/build-your-bot/` — Build simple with Polling — basic bot, `getUpdates` for local dev, SDK links
18. `https://bot.zapps.me/docs/apis/sendSticker/` — sendSticker — `POST .../sendSticker` `chat_id+sticker` from `stickers.zaloapp.com`
19. `https://bot.zapps.me/docs/apis/sendVoice/` — sendVoice — `POST .../sendVoice` `.aac` only, PRIVATE only group silently undelivered

**Pypi + SDK source (primary)**

20. `https://pypi.org/project/python-zalo-bot/` — pypi `python-zalo-bot 0.1.9 2026-01-27` `requires_python >=3.8`, `requires_dist httpx<0.29,>=0.27 + httpcore>=1.0.9; python>=3.14`, `license MIT`, `Homepage https://github.com/yourusername/python-zalo-bot` placeholder, description `based on python-telegram-bot MIT https://github.com/python-telegram-bot/python-telegram-bot`
21. Local wheel `C:\Users\ThongLe\AppData\Local\Temp\opencode\zalo-bot\unzipped\zalo_bot/_bot.py:31-48` — `class Bot.__init__(token,base_url=BASE_URL)` `self._base_url=f"{base_url}/bot{token}"` + `_request=(HTTPXRequest(),HTTPXRequest())`; `zalo_bot/_bot.py:88-109` `get_me` `POST getMe`; `zalo_bot/_bot.py:111-165` `get_update` `POST getUpdates timeout`; `zalo_bot/_bot.py:196-246` `_post/_do_post` `RequestData`; `zalo_bot/_bot.py:248-294` `initialize/shutdown __aenter__`; `zalo_bot/_bot.py:307-410` `send_message/send_photo/send_sticker/send_chat_action` + `set_webhook/delete_webhook/get_webhook_info` via `asyncio.run` — sync shim breaks FastAPI
22. `zalo_bot/constants.py:13,19-20` — `BASE_URL="https://bot-api.zapps.me"` (mismatched vs `bot-api.zaloplatforms.com`) + `ChatAction.TYPING="typing"`
23. `zalo_bot/_update.py:10-35` — `Update.de_json(data)` `message=Message.de_json(data["message"])` `effective_user->from_user`; requires unwrapping `body["result"]` per pypi webhook example `Update.de_json(request.get_json()["result"],bot)`
24. `zalo_bot/_message.py:1-60` — `Message` `message_id,date,chat,text,from_user,photo_url,sticker` `reply_text/reply_photo` via `get_bot()`
25. `zalo_bot/ext/_application.py:1-61` — `Application` `add_handler`, `process_update`, `_polling_loop` `get_update(timeout=30)` + `run_polling() asyncio.run`
26. `zalo_bot/ext/_dispatcher.py:1-33` — `Dispatcher` `add_handler -> Application`, `process_update_sync` `asyncio.run`, `workers` loop — sync anti-pattern for ASGI
27. `zalo_bot/ext/filters.py:1-22` — `BaseFilter` `&|~` + `TEXT,COMMAND,PHOTO,STICKER,ALL`
28. `zalo_bot/ext/_handler.py:11-40` — `CommandHandler` `f"/{command}"`, `MessageHandler(filters,callback)`
29. `zalo_bot/error.py:1-60,92-100` — `ZaloError,InvalidToken,NetworkError,BadRequest,RetryAfter(retry_after)`

**Codebase — file:line (primary)**

* `backend/app/api/zalo.py:25` — `ZALO_API`, `zalo.py:37-38` `_zalo_url`, `zalo.py:30-34` `_get_client`, `zalo.py:41-50` `_zalo_get_me`, `zalo.py:53-68` `_zalo_send_message` 2000 trunc + 429, `zalo.py:71-75` `_zalo_send_chat_action`, `zalo.py:78-91` `ZaloChannelRequest/UpdateRequest`, `zalo.py:108-122` `_to_response`, `zalo.py:128-138` `list_channels`, `zalo.py:141-164` `POST /channels` setWebhook verification 400, `zalo.py:174-192` `PUT`, `zalo.py:206-211` health, `zalo.py:214-230` sync no history, `zalo.py:267-272` `webhook/info`, `zalo.py:274-324` `POST /webhook` header check + event dispatch + `message.unsupported`, `zalo.py:327-351` `_handle_message` chat_id session
* `backend/app/services/zalo_channels.py:18-47` `_ensure_table slug`, `zalo_channels.py:50-73` `_to_dict decrypt`, `zalo_channels.py:76-110` list/get_by_identifier `id|slug|bot_id`, `zalo_channels.py:113-148` `create_channel` bot_id unique + slug dedup, `zalo_channels.py:151-191` `update_channel/update_last_sync_status/delete_channel`
* `backend/app/models/zalo_channel.py:12-33` `ZaloChannelModel` `zalo_channels` + slugify
* `backend/app/services/encryption.py:12-26,29-51` `_get_fernet encrypt/decrypt`
* `backend/app/db/conversation_store.py:20-46` open DB + tables, `conversation_store.py:32-40` `facebook_conversation_links`, `conversation_store.py:50-87` `link_page_to_session/list_sessions_with_meta`, `conversation_store.py:113-130` `add_sync_log/list_sync_logs`, `conversation_store.py:140-159` `save/load_messages`
* `backend/app/api/routes.py:24-25` `zalo.router prefix /zalo`
* `backend/app/core/config.py:44` `encryption_key`, `config.py:9-56` Settings w/o `public_base_url` (add optionally)
* `backend/app/api/facebook.py:36,41-44,55-68,71-88,94-120,123-210,270-504,507-580` reference shape (url, client, send, health, sync, webhook challenge) — Zalo replaces `hub.mode` GET with header POST
* `frontend/src/pages/admin/integrations/index.vue:6,76-83,135-141,216-252,328,476,478-492,717-731` Tabs, schemas, load, connect, Test/Sync, modal, webhook alert
* `backend/pyproject.toml:9,22-23` `httpx>=0.28.0` `cryptography>=49.0`
