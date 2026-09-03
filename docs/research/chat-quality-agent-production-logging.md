# Chat Quality Agent — Production Chat Logging Research

Date: 2026-09-03
Scope: How https://github.com/tanviet12/chat-quality-agent handles chat messages in production — ingestion, persistence, logging, observability hooks, and PII/retention posture. Primary-source only (repo code, README, configs, docs).
Repo: https://github.com/tanviet12/chat-quality-agent
Cloned: `D:\tmp\pi-github-repos\runtime-3LYdOz\e7167c284499aa9ba6f8082400ab257130790bdd7d4e5afc055137f92ed07adb` via `fetch_content url="https://github.com/tanviet12/chat-quality-agent"`
Commit / version file: `VERSION` (image tag on Docker Hub `buitanviet/chat-quality-agent`) — checked `backend/main.go:version = "dev"` default.

## Summary

**CQA is not a live chat server — it is a poll-based quality-analysis pipeline.** Chat interactions are pulled from Zalo OA and Facebook Messenger via channel adapters, upserted durably into MySQL, then fed to Claude/Gemini for QC/classification. There is no real-time message bus, no WebSocket, and no webhook ingress for chat messages in the cloned code path. Production logging is minimal: unstructured `log.Printf` / `gin.Logger()` to stdout + durable DB audit tables (`activity_logs`, `ai_usage_logs`, `notification_logs`, `job_runs`/`job_results`). No structured JSON logger, no OpenTelemetry/Prometheus/Sentry/external log shipper, and no PII redaction or retention policy in code.

---

## 1. How Chat Messages Are Handled in Production

### 1.1 Architecture (primary source)

* **Stack — primary source:** `README.md` table `Backend Go 1.25+ / Gin | Database MySQL 8.0 | AI Claude/Gemini | Reverse Proxy Nginx + Lego | Deploy Docker Compose` and `docker-compose.yml` services `nginx → app (Go+Vue SPA, :8080) → db (mysql:8.0)`. `Dockerfile` multi-stage: `node:20` frontend + `golang:1.25-alpine` backend + `alpine:3.21` runtime with `ca-certificates tzdata`, `EXPOSE 8080`, `ENTRYPOINT ["/app/cqa-server"]`.
* **Entry point — primary source:** `backend/main.go:1-55` loads `config.Load()`, `middleware.SetJWTSecret`, `db.Connect(DSN, IsProduction())`, `db.AutoMigrate()`, starts `engine.NewScheduler` then `api.SetupRouter(cfg)` and `router.Run(ListenAddr())`. `config/config.go:14-22` defaults `SERVER_PORT 8080`, `SERVER_HOST 127.0.0.1`, `TZ Asia/Ho_Chi_Minh` in `docker-compose.yml`.
* **Production switch — primary source:** `backend/config/config.go:55 IsProduction() return Env=="production"`; `backend/api/router.go:13-15` sets `gin.ReleaseMode` when `IsProduction()`, `backend/db/mysql.go:11-14` sets GORM logger to `Warn` in production else `Info`.

### 1.2 Ingestion is poll, not webhook

* **Scheduler — primary source:** `backend/engine/scheduler.go:42-61 Start()` registers a `gocron.DurationJob(5 * time.Minute)` task `syncAllChannelsTask` and cron analysis jobs via `loadCronJobs()`. On startup also `cleanupStuckRuns()` marks any `job_runs.status=="running"` as `failed`.
* **Per-channel throttle — primary source:** `backend/engine/scheduler.go:98-126` reads `channel.metadata.sync_interval` (default 15 min) and skips channels whose `last_sync_at` is still within that interval. Default lookback query uses `WHERE is_active=true`.
* **Sync flow — primary source:** `backend/engine/sync.go:21-101 SyncChannel()` decrypts `channel.credentials_encrypted` via `pkg.Decrypt(..., EncryptionKey)`, builds an adapter via `channels.NewAdapter(channelType, credBytes)`, derives `since = last_sync_at - 1h` or 7 days ago, calls `adapter.FetchRecentConversations(ctx, since, 100)` then per-conversation `adapter.FetchMessages(ctx, conv.ExternalID, since)`. Total counts logged with `log.Printf("[sync] ... found %d conversations ... synced %d conversations, %d messages")`.
* **Adapter interface — primary source:** `backend/channels/adapter.go:8-35` defines `ChannelAdapter { FetchRecentConversations, FetchMessages, HealthCheck }` and data types `SyncedConversation { ExternalID, ExternalUserID, CustomerName, LastMessageAt }` / `SyncedMessage { ExternalID, SenderType, SenderName, Content, ContentType, Attachments, RawData }`. Implementations in `backend/channels/zalo_oa.go` and `backend/channels/facebook.go` (registered in `backend/channels/registry.go`).
* **OAuth callbacks exist but are for channel connect, not message ingress — primary source:** `backend/api/router.go:76-77` `GET /api/v1/channels/zalo/callback` / `facebook/callback` handlers in `backend/api/handlers/channels.go` — they exchange OAuth codes for tokens and persist encrypted credentials, they do not receive chat webhooks.

### 1.3 Message persistence (durable, not transient)

* **GORM models — primary source:** `backend/db/models/message.go:5-18` `Message { ID char(36) PK, TenantID, ConversationID, ExternalMessageID varchar(255), SenderType customer|agent|system, SenderName varchar(500), SenderExternalID varchar(255), Content text, ContentType default text, Attachments json, SentAt indexed, RawData json, CreatedAt }` with composite index `idx_msg_conv_time(conversation_id, sent_at)`. `backend/db/models/conversation.go:5-20` `Conversation { ID, TenantID, ChannelID, ExternalConversationID, ExternalUserID, CustomerName varchar(500), LastMessageAt indexed, MessageCount, Metadata json }`. `backend/db/models/channel.go:5-20` `Channel { CredentialsEncrypted varbinary(2048), LastSyncAt, LastSyncStatus, LastSyncError text }`.
* **Dedup / idempotency — primary source:** `backend/db/mysql.go:48-66 addUniqueConstraints()` via `ALTER TABLE ... ADD UNIQUE INDEX` on `channels(tenant_id, channel_type, external_id)`, `conversations(tenant_id, channel_id, external_conversation_id)`, `messages(tenant_id, conversation_id, external_message_id)`. `backend/engine/sync.go:147-175 upsertConversation()` and `178-232 upsertMessage()` do `WHERE ... First(&existing)` then `Updates` or `Create(NewUUID())`. Messages dedup on `external_message_id`; existing rows only get attachment path updates.
* **Raw payload stored — primary source:** `backend/engine/sync.go:226-239` `rawDataJSON, _ := json.Marshal(msg.RawData)` then `RawData: string(rawDataJSON)` on `models.Message`. `backend/channels/facebook.go:195` and `zalo_oa.go:280` populate `RawData: msg` (the full upstream JSON) — so the original external payload is retained verbatim in MySQL `messages.raw_data` (type json).
* **Attachment persistence — primary source:** `backend/engine/sync.go:136-148` checks `channel.metadata.sync_files` bool; if true calls `downloadAttachments()` which writes to local disk ` /var/lib/cqa/files/{tenantID}/{convID}/{name}` (`os.MkdirAll 0755`, `http.Client 30s`, path-traversal guard via `filepath.Clean` + `HasPrefix` check). `docker-compose.yml: volumes: file_storage:/var/lib/cqa/files` persists this across restarts. `backend/api/router.go:34-74` serves files at `GET /api/v1/files/*filepath` behind `JWTAuth()` + tenant-ownership check.
* **DB connection — primary source:** `backend/db/mysql.go:8-33 Connect()` opens `gorm.Open(mysql.Open(dsn))` with `MaxIdleConns 10 / MaxOpenConns 100`, logs `Database connected successfully`.

### 1.4 What "production logging of interactions" actually means here

There are two distinct layers — conflated by the question, separated in the code:

1. **Durable message store (MySQL)** — the authoritative log of every chat interaction (see §1.3). This is the production source of truth, not a sidecar log.
2. **Ephemeral process logs (stdout)** — `log.Printf` / `gin.Logger()` lines for ops debugging (see §2). These are not persisted by the app.

---

## 2. How Chat Interactions Are Logged

### 2.1 Durable interaction log: MySQL tables

| Table | Purpose | Key fields | Source |
|-------|---------|------------|--------|
| `messages` | Every synced chat message | `content text`, `raw_data json`, `attachments json`, `sent_at`, `sender_type/name` | `backend/db/models/message.go` |
| `conversations` | Thread grouping | `customer_name`, `last_message_at`, `message_count`, `metadata json` | `backend/db/models/conversation.go` |
| `channels` | Sync watermark | `last_sync_at`, `last_sync_status`, `last_sync_error` | `backend/db/models/channel.go` |
| `job_results` | AI output per conversation | `result_type qc_violation|classification_tag|conversation_evaluation`, `severity`, `rule_name`, `evidence text`, `detail json`, `ai_raw_response text`, `confidence` | `backend/db/models/job.go:43-58` |
| `job_runs` | Run aggregate | `status running|success|error|failed`, `summary json`, `error_message` | `backend/db/models/job.go:30-41` |

* Verdict: **no separate file log, no external service (Elasticsearch, Loki, CloudWatch, Datadog) for chat content** — the DB is the log. `docker-compose.yml` has no logging driver, no sidecar, no volume for log files.

### 2.2 Transient process logs: stdout via stdlib + Gin

* **Library — primary source:** No `logrus`/`zap`/`zerolog`/`slog` in `backend/go.mod` — only stdlib `log` and `gin.Logger()`. `backend/api/router.go:19-21` `r.Use(gin.Logger())` + `r.Use(gin.Recovery())`. All other logging is `log.Printf("[sync] ...")`, `log.Printf("[analyzer] ...")`, `log.Printf("[security] ...")`.
* **What is emitted for chat — primary source:** `backend/engine/sync.go:23 log.Printf("[sync] starting sync for channel %s (%s)", ...)`; `sync.go:64 channel %s: found %d conversations`; `sync.go:70 sync_files=%v`; `sync.go:119 synced %d conversations, %d messages`; errors like `upserting conversation/message` and download results. `backend/engine/analyzer.go:133` per-job conversation counts and `log.Printf("[analyzer] AI error for conversation %s: %v")`.
* **Security-tagged stdout lines — primary source:** `backend/api/middleware/auth.go:117`, `ratelimit.go:90`, `tenant.go:32`, `backend/api/router.go:70` emit `[security] ... ip=... path=...` for JWT failures, rate-limit, tenant denial, file-access denial — but these go to stdout, not to `activity_logs`.
* **Production behavior — primary source:** `backend/config/config.go:55` + `backend/api/router.go:14` switch Gin to release mode; `backend/db/mysql.go:12-14` downgrades GORM logging from `Info` to `Warn`. No JSON formatter, no log level env var beyond `APP_ENV`, no rotation config in `docker-compose.yml` or `Dockerfile` — container stdout is expected to be collected by the host's Docker logging driver (default `json-file`, not configured here).

### 2.3 Audit / activity logs (DB, not stdout)

* **Model — primary source:** `backend/db/models/activity_log.go:5-18` `ActivityLog { id, tenant_id indexed, user_id, user_email, action varchar(50) indexed, resource_type, resource_id, detail text, error_message text, ip_address varchar(45), created_at indexed }`. Index `idx_activity_tenant_created`.
* **Writer — primary source:** `backend/db/activity.go:6-18 LogActivity(tenantID, userID, userEmail, action, resourceType, resourceID, detail, errMsg, ip string)` does `DB.Create(&ActivityLog{...})`. Called from `backend/engine/sync.go:122 LogActivity(... "sync.completed"...)` and `sync.go:140 sync.error`, `backend/engine/analyzer.go:70 job.run.started`, `analyzer.go:247 job.run.completed`, `scheduler.go:129 sync.error/completed`, and handlers `auth.go:249 user.login`, `channels.go:238 channel.delete`, `jobs.go:213 job.delete`, etc.
* **Reader — primary source:** `backend/api/handlers/activity_logs.go:8-36 ListActivityLogs` exposes `GET /api/v1/tenants/:tenantId/activity-logs?page&per_page&action` filtered by `tenant_id` and optional `action LIKE ?%`, ordered `created_at DESC`.
* **Other durable observability tables — primary source:** `backend/db/models/setting.go:14-27 AIUsageLog { tenant_id, job_id, job_run_id, provider, model, input_tokens, output_tokens, cost_usd decimal(10,6), created_at }` written per AI call in `backend/engine/analyzer.go:155-167` and batch path `analyzer.go:340-352`; `NotificationLog { channel_type telegram|email, recipient, subject, body text, status sent|failed }` written by `backend/notifications/`.

### 2.4 API access to conversations/messages

* **List — primary source:** `backend/api/handlers/conversations.go:11-90 ListConversations` paginated `GET /tenants/:tenantId/conversations?page&per_page&channel_id&channel_type&search&evaluation` with filters for evaluated state via `job_results` subqueries.
* **Messages — primary source:** `conversations.go:92-138 GetConversationMessages` verifies `conversation.tenant_id`, then `WHERE conversation_id AND tenant_id ORDER BY sent_at ASC` with VN timezone formatting `pkg.ToVN(...).Format("2006-01-02T15:04:05+07:00")`.
* **Evaluations — primary source:** `conversations.go:155-228 GetConversationEvaluations` groups `job_results` by `job_run_id` with job metadata join.
* **Export — primary source:** `conversations.go:242-360 ExportMessages` for `GET /conversations/export?from&to&format=txt|csv` — builds plain-text or CSV (with UTF-8 BOM) from the DB, not from log files.

---

## 3. Middleware, Interceptors, Observability Hooks

### 3.1 HTTP middleware chain (Gin)

Order in `backend/api/router.go:18-51 SetupRouter()`:

1. `gin.Logger()` — request method/path/status/latency to stdout (Gin default format, not structured JSON) — `router.go:20`.
2. `gin.Recovery()` — panic recovery — `router.go:21`.
3. Static file serving (production only) — `router.go:24-37` with SPA fallback.
4. File serving guard `GET /api/v1/files/*filepath` with `JWTAuth()` + tenant ownership + path-traversal checks — `router.go:39-74`.
5. `corsMiddleware(cfg)` — in production only allows `Origin` containing `c.Request.Host`; sets `Access-Control-Allow-*` — `router.go:152-175`.
6. `middleware.RateLimit(cfg.RateLimitPerIP)` — `router.go:48` (default 500/min/IP, 1000/min/user — `config/config.go:26-28`), backed by in-memory `map[string]*visitor` with `sync.Mutex` and 1-min cleanup goroutine — `backend/api/middleware/ratelimit.go:13-58`. Logs `rate limit exceeded` to stdout; no distributed store (Redis) — per-instance only.
7. `securityHeaders()` — `X-Content-Type-Options nosniff`, `X-Frame-Options DENY`, `HSTS`, `CSP`, `Permissions-Policy` — `router.go:177-189`.
8. Per-route `middleware.JWTAuth()` (15-min access token HS256, 7-day refresh with `token_version`) — `backend/api/middleware/auth.go:28-110` and `TenantContext()`/`RequireRole`/`RequirePermission` — `backend/api/middleware/tenant.go`.

* **No request/response body interceptor** — there is no middleware that logs chat message bodies. The only body-adjacent logging is security events (JWT failures, tenant denials). No `otelgin`, no `ginprom`, no tracing middleware found via grep of `backend/**/*.go`.

### 3.2 Scheduler hooks

* **Post-sync trigger — primary source:** `backend/engine/scheduler.go:148-180 TriggerAfterSyncJobs(tenantID, channelID)` invoked at end of `sync.go:126 GetDefaultScheduler().TriggerAfterSyncJobs(...)` — fans out to `after_sync` jobs whose `input_channel_ids` contains the channel, each in its own goroutine with `context.WithTimeout 30m` and panic recovery.
* **Cron analysis — primary source:** `scheduler.go:133-170 loadCronJobs()` reads `jobs WHERE is_active=true AND schedule_type='cron' AND schedule_cron!=''` and registers `gocron.CronJob("TZ=<tenant timezone> <cron>")` tasks that call `NewAnalyzer(cfg).RunJob`.
* **Analyzer hooks — primary source:** `backend/engine/analyzer.go:58-260 runJobInternalExt()` writes incremental `job_runs.summary` JSON progress (`conversations_found/analyzed/passed/errors/issues_found`) for polling, logs `AIUsageLog` per batch/call, and dispatches `notifications.NewDispatcher().SendJobResults()` when `output_schedule != "none"`.

### 3.3 What is *not* present (explicit negative findings)

* No OpenTelemetry, Prometheus metrics, Sentry, Datadog, CloudWatch, ELK/Loki sidecar — verified by absence in `backend/go.mod`, `docker-compose.yml`, `Dockerfile`, and code grep for `otel|trace|span|metric|sentry|logrus|zap`.
* No structured JSON logging library — all logs are `log.Printf("%s", ...)` plaintext.
* No Nginx access-log customization — `docker/nginx.conf` has only `proxy_pass` and security headers, no `access_log`/`error_log` directives, no JSON log format.
* No webhook endpoint that receives inbound chat messages — `backend/api/router.go` has no `POST /webhook` route; Zalo/Facebook integrations are pull-only.

---

## 4. Message Persistence vs Transient Logging

| Concern | Durable (MySQL) | Transient (stdout/logs) | Source |
|---------|----------------|------------------------|--------|
| Chat content | `messages.content` + `raw_data` + `attachments` via `upsertMessage` | `log.Printf("[sync] ... %d messages")` counts only, not content | `backend/engine/sync.go:178-232`, `backend/db/models/message.go` |
| Conversation metadata | `conversations` row with `message_count`, `last_message_at` | Not logged | `backend/engine/sync.go:186` |
| AI judgments | `job_results` (one row per violation/tag + one `conversation_evaluation` per conversation, with `ai_raw_response`) | `log.Printf("[analyzer] AI error ...")` on failure only | `backend/engine/analyzer.go:188-330` |
| Ops audit | `activity_logs` (login, sync, job run, notification.error) | `[security]` stdout lines duplicated for some events | `backend/db/activity.go`, `backend/api/middleware/auth.go:117` |
| Cost | `ai_usage_logs` with token counts + `CalculateCostUSD` | Not in stdout | `backend/db/models/setting.go:28-40`, `backend/ai/provider.go:20-46` |
| Notifications | `notification_logs` | `log.Printf("[analyzer] notification error ...")` | `backend/notifications/` |
| Retention | Permanent in MySQL (no TTL) unless manually purged | Container stdout tied to Docker `json-file` rotation (host-level, not app-level) | `docker-compose.yml`, `backend/api/handlers/channels.go:271 PurgeChannelConversations`, `backend/api/handlers/jobs.go:237 ClearJobResults` |

* **Implication:** The DB is the only production chat log with durability guarantees. Stdout logs are ephemeral and contain only counts/status, never message bodies (checked via grep — no `msg.Content` in any `log.Printf` call).

---

## 5. PII Handling, Retention, Privacy Considerations

### 5.1 What PII is stored and how

* **Stored PII fields — primary source:** `Message.SenderName varchar(500)`, `SenderExternalID varchar(255)`, `Content text`, `Conversation.CustomerName varchar(500)`, `ExternalUserID varchar(255)`, `RawData json` (full upstream payload which may contain phone, email, profile data depending on Zalo/Facebook response). `User.Email varchar(255) uniqueIndex`, `User.Name`. All in plaintext in MySQL — `backend/db/models/message.go`, `conversation.go`, `user.go`.
* **Encrypted at rest — primary source:** Only `Channel.CredentialsEncrypted varbinary(2048)` (Zalo/Facebook tokens) and `AppSetting.ValueEncrypted` (AI API keys, `ENCRYPTION_KEY` 32 bytes AES-256-GCM via `backend/pkg/crypto.go:8-48`) are encrypted. `pkg.Encrypt/Decrypt` use `aes.NewCipher` + `cipher.NewGCM` with random nonce prepended. Channel credentials are encrypted before `DB.Create` in `backend/api/handlers/channels.go:131-165` and decrypted only in `engine/sync.go:26-27` and `analyzer.go:getProvider`. **Chat messages themselves are not encrypted.**
* **Masking on read — primary source:** `backend/pkg/helpers.go:31-41 MaskSecret()` shows only last 4 chars (`****3xyz`), used in `backend/api/handlers/settings.go:30` when returning encrypted settings. `Channel.CredentialsEncrypted json:"-"` and `User.PasswordHash json:"-"` are omitted from JSON API responses via struct tag. Messages have no such masking — `handlers/conversations.go:109-138` returns `content` verbatim to any caller with `messages:r` permission.
* **File PII — primary source:** Attachments downloaded to `/var/lib/cqa/files/{tenantID}/{convID}/{name}` on host volume `file_storage` — `backend/engine/sync.go:253-332` — and served via `GET /api/v1/files/*filepath` with JWT + `UserTenant` membership check and `filepath.Clean` traversal guard.

### 5.2 Retention and deletion

* **No automatic retention/TTL — primary source:** No `DELETE ... WHERE created_at <` job, no cron purge, no `retention_days` setting found in `backend/config/config.go`, `models`, or `engine/scheduler.go`. `ActivityLog`, `Message`, `Conversation`, `JobResult` rows accumulate indefinitely in MySQL `mysql_data` volume.
* **Manual purge endpoints — primary source:** `backend/api/router.go:67` `DELETE /tenants/:tenantId/channels/:channelId/conversations` handled by `backend/api/handlers/channels.go:271 PurgeChannelConversations` (deletes `file_storage` dir + `messages` + `conversations` for that channel, gated by `RequirePermission("channels","d")` and `owner/admin`); `backend/api/handlers/jobs.go:237 Delete ClearJobResults` and `269 ClearJobRuns` (delete `job_results`/`job_runs` per job); full tenant delete in `backend/api/handlers/tenants.go:196` cascades `ActivityLog` etc. No cross-tenant wipe, no "forget user" by external ID.
* **No anonymization on delete** — deletions are hard deletes (`tx.Delete`), not soft-delete/redaction. No hashing of `customer_name` after retention expiry.

### 5.3 Other privacy-relevant controls

* **Multi-tenant isolation — primary source:** Every query scopes by `tenant_id` (`conversations.go:17 WHERE conversations.tenant_id=?`, `GetConversationMessages` verifies `conversation.tenant_id`), enforced by `TenantContext` middleware checking `user_tenants` membership — `backend/api/middleware/tenant.go:11-30`. Unique constraints are per-tenant (`backend/db/mysql.go:48-66`). File serving checks `UserTenant` membership — `router.go:62-67`.
* **No consent/tracking disclosure in code** — README/docs describe syncing business-owned Zalo OA/Facebook pages (where the tenant controls the page token) — not end-user consent flows. No DPA/consent text found in `backend/` source.
* **Nginx does not log bodies** — `docker/nginx.conf` and `docker/Dockerfile.nginx` show only proxy headers (`X-Real-IP`, `X-Forwarded-For/Proto`), no body logging — so chat content does not leak into proxy access logs either.

### 5.4 Gaps to note (for consumers of this system)

* Chat `content` + `raw_data` are long-lived plaintext PII with no encryption-at-rest and no retention expiry — assess GDPR/Vietnam PDPD exposure if personal data flows through Zalo/Facebook chats.
* Activity logs store `ip_address varchar(45)` — itself PII under GDPR — with no truncation.
* No audit for message reads — `ListConversations`/`GetConversationMessages` do not emit `activity_logs` entries (only writes like login, channel delete, job delete are logged — `activity_logs.go` has no read path hook).

---

## Verification

* `fetch_content url="https://github.com/tanviet12/chat-quality-agent"` — cloned successfully; repo is public and non-empty (139 backend Go files listed).
* `backend/db/models/message.go`, `conversation.go`, `channel.go`, `activity_log.go`, `job.go`, `setting.go` — read and cited above.
* `backend/engine/sync.go`, `analyzer.go`, `scheduler.go` — read and cited.
* `backend/api/router.go`, `backend/api/middleware/auth.go:ratelimit.go:tenant.go`, `backend/api/handlers/conversations.go:activity_logs.go:channels.go` — read and cited.
* `backend/config/config.go`, `backend/db/mysql.go`, `backend/pkg/crypto.go:helpers.go`, `backend/channels/adapter.go` — read and cited.
* `docker-compose.yml`, `docker/nginx.conf`, `Dockerfile`, `.env.example` — read and cited.
* Negative checks: `Select-String` for `structured|logrus|zap|sentry|opentelemetry|otel|prometheus` and for `PII|retention|gdpr|anonym` — only `MaskSecret` hit — documented in §3.3/§5.

## Sources

* `https://github.com/tanviet12/chat-quality-agent` — repo root (primary)
* `https://github.com/tanviet12/chat-quality-agent/blob/main/README.md`
* `https://github.com/tanviet12/chat-quality-agent/blob/main/docker-compose.yml`
* `https://github.com/tanviet12/chat-quality-agent/blob/main/Dockerfile`
* `https://github.com/tanviet12/chat-quality-agent/blob/main/docker/nginx.conf`
* `https://github.com/tanviet12/chat-quality-agent/blob/main/.env.example`
* `backend/main.go` — entry point, scheduler start
* `backend/config/config.go` — `Load()`, `IsProduction()`, `APP_ENV/ENCRYPTION_KEY/JWT_SECRET` validation
* `backend/db/mysql.go` — `Connect()`, `AutoMigrate()`, `addUniqueConstraints()`, connection pool
* `backend/db/models/message.go` — `Message` schema
* `backend/db/models/conversation.go` — `Conversation` schema
* `backend/db/models/channel.go` — `Channel` schema (`CredentialsEncrypted`)
* `backend/db/models/activity_log.go` — `ActivityLog` schema
* `backend/db/models/job.go` — `Job`, `JobRun`, `JobResult` schemas
* `backend/db/models/setting.go` — `AIUsageLog`, `NotificationLog`, `AppSetting`
* `backend/db/models/user.go` — `User`, `UserTenant` RBAC
* `backend/db/models/tenant.go` — `Tenant` schema
* `backend/db/activity.go` — `LogActivity()` writer
* `backend/engine/sync.go` — `SyncChannel`, `upsertConversation/Message`, `downloadAttachments`
* `backend/engine/analyzer.go` — `runJobInternalExt`, `saveResults`, `runBatchMode`, `AIUsageLog` writes
* `backend/engine/scheduler.go` — `Start()`, `syncAllChannelsTask()`, `TriggerAfterSyncJobs()`, `cleanupStuckRuns()`
* `backend/channels/adapter.go` — `ChannelAdapter` interface, `SyncedMessage/Conversation`
* `backend/channels/facebook.go`, `backend/channels/zalo_oa.go`, `backend/channels/registry.go` — provider implementations
* `backend/api/router.go` — `SetupRouter()`, middleware chain, `CORS/securityHeaders/file serving`
* `backend/api/middleware/auth.go` — `JWTAuth`, `GenerateAccessToken/RefreshToken` (HS256, 15m/7d)
* `backend/api/middleware/tenant.go` — `TenantContext`, `RequireRole/RequirePermission`
* `backend/api/middleware/ratelimit.go` — in-memory token bucket (500 IP / 1000 user per min)
* `backend/api/handlers/conversations.go` — `ListConversations`, `GetConversationMessages`, `ExportMessages`
* `backend/api/handlers/activity_logs.go` — `ListActivityLogs`
* `backend/pkg/crypto.go` — `Encrypt/Decrypt` AES-256-GCM
* `backend/pkg/helpers.go` — `MaskSecret`, `ToVN`, `NewUUID`
* `backend/ai/provider.go` — `AIProvider`, `CalculateCostUSD`
* `backend/ai/prompts.go` — `BuildQCPrompt`, `FormatChatTranscript`
* `backend/ai/retry.go` — `withRetry` exponential backoff 5s→15s→45s

## Alternatives Considered

* None — scope is research, not a build decision.
