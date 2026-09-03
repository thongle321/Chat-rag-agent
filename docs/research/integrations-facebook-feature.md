# Integrations Facebook Feature Research — chat-rag-agent vs tanviet12/chat-quality-agent

Date: 2026-08-26
Scope: Redesign Integrations UI to be modern; extract Facebook *feature* (not UI) from https://github.com/tanviet12/chat-quality-agent/tree/main/backend

## Summary

Your `chat-rag-agent` already has a working Facebook feature: manual paste of Page ID + Page Token + Verify Token, persisted as single row `id=1`, webhook `GET /webhook` verification + `POST /webhook` push to `answer_question`. The external Go repo has **no webhook** — it polls Graph API (`FetchRecentConversations`/`FetchMessages`), encrypts credentials (AES-256-GCM), and adds OAuth code→long-lived Page token exchange with HMAC state and a `HealthCheck`. For a modern integrations UI, keep your webhook-push (better latency) and **borrow their OAuth, health check, encrypted storage, and polling backfill** — but rebuild the UI from `@nuxt/ui v4` that you already ship, not their Go table UI.

---

## 1. Current chat-rag-agent — primary sources

* **UI** `frontend/src/pages/admin/integrations.vue:1-282` — `channels[]` single element `GET /facebook/config` (`integrations.vue:72`), `connectSchema`/`editSchema` zod `page_name/page_id/page_token/verify_token` (`integrations.vue:21-45`), 3 modals (Connect/Edit/Disconnect) each with `UForm` + 4 `UInput`, empty state `i-lucide-plug` `No channels connected`, connected `UCard` `page_name` + `Page ID` + `Connected` `UBadge`, no webhook URL shown, no health/verify status.
* **Backend API** `backend/app/api/facebook.py:21` `FB_GRAPH_API="https://graph.facebook.com/v25.0"`; `_get_client()` `AsyncClient timeout30` `facebook.py:26-30`; `send_message` `POST /{page_id}/messages?access_token` `facebook.py:38-51`; `mark_seen`/`typing_on` `sender_action` `facebook.py:53-69`; models `FacebookConfigRequest/Response` `facebook.py:79-91`; `GET /config` 404 if none `facebook.py:97-108`; `POST /config` `save_facebook_config` `facebook.py:111-126`; `DELETE /config` `facebook.py:129-134`; webhook `GET /webhook` `hub.mode==subscribe && verify_token==stored → challenge` `facebook.py:141-167`; `POST /webhook` `object=="page"` else 404, loop `entry[].messaging[]` skip `sender==page_id`, `asyncio.create_task(_handle_message)` `facebook.py:170-209`; `_handle_message` `mark_seen+typing_on` → `answer_question(text, session_id=sender_id):219` trim 2000 → `send_message` `facebook.py:212-236`.
* **DB** `backend/app/models/facebook_config.py:7-14` `id=1, page_id, page_name, page_token, verify_token` plaintext; service `backend/app/services/facebook_config.py:11-67` single-row CRUD commit.
* **Nav** `frontend/src/layouts/default.vue:18-23` one `Integrations i-lucide-plug` route; `pyproject.toml:23` `cryptography>=49.0.0` already available for encryption.

## 2. External tanviet12/chat-quality-agent — primary sources (Go, not UI)

Fetched via `webfetch` on `raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/*`:

* **Adapter** `backend/channels/facebook.go` `fbGraphBase="https://graph.facebook.com/v21.0"` (raw `…/channels/facebook.go`), `FacebookCredentials{PageID,AccessToken}`, `doRequest(ctx,url)` `GET` injects `access_token`, `FetchRecentConversations` `GET /{page_id}/conversations?fields=id,link,updated_time,participants&limit=100` cursor `paging.next`, filters `since`, extracts `customerName` where `id != PageID`; `FetchMessages` `GET /{conversationID}/messages?fields=id,message,from,to,created_time,attachments,shares,sticker&limit=100` parses `senderType agent if from.id==PageID`, attachments with 5 fallbacks `image_data.url/video_data.url/file_url/url/media.image.src`; `HealthCheck` `GET /{page_id}?fields=id,name`.
* **No webhook** — `backend/api/router.go` line 85 + `backend/api/handlers/channels.go:FacebookOAuthCallback` only `GET /api/v1/channels/facebook/callback` & `GET /channels/zalo/callback`; sync is polling.
* **Sync engine** `backend/engine/sync.go:SyncChannel` decrypt → `NewAdapter` → `FetchRecentConversations(since=LastSyncAt-1h,limit100)` → `upsertConversation` → `FetchMessages` → `upsertMessage` dedup `external_message_id` → `downloadAttachments /var/lib/cqa/files/{tenant}/{conv}`; `backend/engine/scheduler.go` `gocron every 5m` `syncAllChannelsTask` per-channel `metadata.sync_interval default 15m`; manual `POST /channels/:id/sync` async 10m.
* **Token/storage** `backend/db/models/channel.go:Channel{CredentialsEncrypted varbinary(2048)}`; `backend/config/config.go:ENCRYPTION_KEY must 32 bytes AES-256-GCM`, `JWT_SECRET >=32`; `handlers/channels.go:CreateChannel` encrypt JSON then `GET /me/accounts?access_token=userToken` → exchange to Page token; OAuth `FacebookOAuthCallback` → `exchangeFacebookCode POST /oauth/access_token` → `getLongLivedFBToken grant_type=fb_exchange_token` → `getFBPageToken` → update `credentials_encrypted,external_id,name,redirect ?fb_auth=success`; Zalo auto `OnTokenRefresh`, Facebook long-lived ~60d manual `POST /channels/:id/reauth scope=pages_show_list,pages_messaging,…`; HMAC state `signOAuthState(tenant:channel:hmac(JWT_SECRET)[:16])`.
* **Quality** `backend/engine/analyzer.go:Analyzer` formats `transcript [HH:MM] Sender: Content` (`ai.FormatChatTranscript`), `BuildQCPrompt/BuildClassificationPrompt` (`ai/prompts.go`), `AnalyzeChatBatch 5`, saves `job_results {verdict PASS/FAIL/SKIP, violations[severity,rule,evidence,suggestion]}` — no RAG vector store; AI `ai/{claude.go,gemini.go,provider.go}` `anthropic-sdk-go v1.27, genai v1.51`.

## 3. Feature vs UI split

| External thing | Is it a *feature* (borrow)? | Is it *UI* (don't copy)? |
|---|---|---|
| OAuth code→long-lived Page token + HMAC state | yes — replaces manual paste | no — keep your modals as fallback, add `Connect with Facebook` button |
| `HealthCheck` + `has_token` masking | yes | no — surface as badge/toast, not their table |
| AES-256-GCM `CredentialsEncrypted` | yes | no |
| Polling `FetchRecentConversations`/`FetchMessages` cursor | yes as backfill supplement to your webhook push | no — no need for their scheduler UI |
| `UTabs`/`UPageCard` multi-channel grid | no — that's UI | yes — build new from `@nuxt/ui` you ship |
| QC `analyzer.go` batch verdicts | no — your RAG already answers | no |

## 4. What to add (5 small features, ponytail minimal)

1. **OAuth connect** — `GET /facebook/oauth/url` builds `https://www.facebook.com/v25.0/dialog/oauth?client_id&redirect_uri&scope=pages_show_list,pages_messaging,pages_read_engagement,pages_manage_metadata&state=hmac`; `GET /facebook/callback?code&state` exchanges → `POST https://graph.facebook.com/v25.0/oauth/access_token` (code) → `GET …/oauth/access_token?grant_type=fb_exchange_token` (long-lived) → `GET /me/accounts` pick page token — port of `handlers/channels.go:FacebookOAuthCallback`. Keep manual modal as fallback.
2. **Health check** — `GET /facebook/health` → `GET https://graph.facebook.com/v25.0/{page_id}?fields=id,name&access_token=page_token` (`HealthCheck` in `facebook.go`) — toggles `success|error` badge + toast `Test connection`.
3. **Encrypted storage** — use existing `cryptography>=49.0.0` (`pyproject.toml:23`): `Fernet` or `AESGCM` with `ENCRYPTION_KEY` 32 bytes from `env` (mirror `config.go`), encrypt `page_token` at rest; decrypt only in `send_message/_handle_message`. No schema migration if you encrypt in-place (store base64 at `page_token`).
4. **Webhook visibility** — UI shows copyable `GET {API_BASE}/api/facebook/webhook` + `verify_token` + `verified` boolean (already computable via `GET /webhook` verification logic `facebook.py:148-160`).
5. **Polling backfill (deferred)** — optional `POST /facebook/sync` porting `FetchRecentConversations(since=24h,limit100)` + `FetchMessages` — useful if webhook misses; schedule via `APScheduler` only if `webhook` 404s observed.

## 5. Modern UI sketch (not copied)

`@nuxt/ui v4` (`frontend/package.json:14`) — `UDashboardPanel` keeps header, body becomes `UTabs [Facebook|Zalo OA disabled]`. Facebook tab: `UPageCard` header icon `i-lucide-facebook` + `UBadge` health; if disconnected: `UAlert` 3-step `USteps` + primary `UButton` `Connect with Facebook` + divider `or paste token manually` (existing modal). If connected: stats grid `page_name | page_id masked | has_token | verify_token masked | last webhook at` + actions `Test connection | Edit (UDrawer) | Disconnect | Copy webhook`. Diagnostics timeline for last webhook `POST` log.

## 6. Verification

* `ruff check backend/app/api/facebook.py backend/app/services/facebook_config.py`
* `pnpm build` (`frontend/package.json:7`)
* Manual: `GET /facebook/health` → `ok` with good token, `error (#190)` with bad; `GET /webhook?hub.mode=subscribe&hub.verify_token=…` → `challenge`; `POST /webhook` `object=page` → `_handle_message` log + reply.
* OAuth: click `Connect with Facebook` → redirect → `GET /facebook/callback?code=` → `GET /facebook/config` shows `has_token true`.

## Sources — primary only

* Repo: `frontend/src/pages/admin/integrations.vue:1-282`, `backend/app/api/facebook.py:21,38,53,79,97,111,129,141,170,212`, `backend/app/models/facebook_config.py:7`, `backend/app/services/facebook_config.py:11`, `backend/pyproject.toml:23`, `frontend/package.json:14`, `frontend/src/layouts/default.vue:18`
* External: `https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/channels/facebook.go` (`fbGraphBase v21.0`, `FetchRecentConversations`, `FetchMessages`, `HealthCheck`), `https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/channels/adapter.go`, `https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/channels/registry.go`, `https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/api/router.go` (no webhook), `https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/api/handlers/channels.go` (`FacebookOAuthCallback`, `exchangeFacebookCode`, `getLongLivedFBToken`, `getFBPageToken`, HMAC state), `https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/engine/sync.go`, `https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/engine/scheduler.go`, `https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/db/models/channel.go`, `https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/config/config.go`, `https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/go.mod`
* Docs: `https://developers.facebook.com/docs/graph-api` (`/me/accounts`, `oauth/access_token`, `grant_type=fb_exchange_token`, `paging.next`), `https://developers.facebook.com/docs/messenger-platform/webhooks` (hub.verify_token flow)
