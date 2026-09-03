# CQA Database Design — Research & Single-File Redesign for RAG (Single-Tenant)

**Date:** 2026-09-03 · **Update:** 2026-09-03 single-tenant revision (no `tenant_id`)  
**Source repo:** https://github.com/tanviet12/chat-quality-agent (Go 1.25+/Gin + GORM + MySQL 8.0)  
**Scope:** What to adapt from CQA into this Document RAG chatbot (FastAPI + pydantic-ai + SQLite + Chroma + BM25) and how to consolidate into **one SQLite file** — **single-tenant only** (no `tenant_id` column).

---

## 1. How this was researched

Primary sources (raw files via `web_fetch`):

- `backend/db/mysql.go` — `AutoMigrate()` + `addUniqueConstraints()` [@raw/mysql.go](https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/db/mysql.go)
- `backend/db/models/channel.go` [@raw/channel.go](https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/db/models/channel.go)
- `backend/db/models/conversation.go` [@raw/conversation.go](https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/db/models/conversation.go)
- `backend/db/models/message.go` [@raw/message.go](https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/db/models/message.go)
- `backend/db/models/job.go` [@raw/job.go](https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/db/models/job.go)
- `backend/db/models/setting.go` [@raw/setting.go](https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/db/models/setting.go)
- `backend/db/models/user.go` / `tenant.go` / `activity_log.go` [@raw/user.go](https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/db/models/user.go) · [@raw/tenant.go](https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/db/models/tenant.go) · [@raw/activity_log.go](https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/db/models/activity_log.go)
- Current RAG: `backend/app/db/session.py`, `backend/app/db/conversation_store.py`, `backend/app/models/{user,session,ai_settings,chat_logging}.py`

---

## 2. CQA database at a glance

| Property | Value |
|----------|-------|
| Engine | MySQL 8.0, GORM `AutoMigrate` |
| Pool | `SetMaxIdleConns(10)`, `SetMaxOpenConns(100)` — `mysql.go:22-23` |
| Migration | Code-first, not SQL files |
| Unique indexes | `ALTER TABLE ... ADD UNIQUE INDEX` in `addUniqueConstraints()` |
| PK | `char(36)` UUID everywhere |

**16 tables** in `mysql.go:26-44`: `User, Tenant, UserTenant, Channel, Conversation, Message, Job, JobRun, JobResult, AppSetting, NotificationLog, AIUsageLog, OAuthClient, OAuthAuthorizationCode, OAuthToken, ActivityLog`

**Original tenant-scoped uniques** (`mysql.go:47-62`):
- `channels: (tenant_id, channel_type, external_id)`
- `conversations: (tenant_id, channel_id, external_conversation_id)`
- `messages: (tenant_id, conversation_id, external_message_id)`

> **Single-tenant adaptation:** Drop `tenant_id` entirely. Uniques become `(channel_type, external_id)`, `(channel_id, external_conversation_id)`, `(conversation_id, external_message_id)`. No sentinel tenant, no `DEFAULT_TENANT`.

---

## 3. Current RAG store — fragmented

| Location | What | Gap vs CQA |
|----------|------|------------|
| `backend/data/app.db` (`sqlite+aiosqlite`, `Base.metadata.create_all()`) | `user`, `chat_sessions(id,title,pinned)`, `ai_settings` (single-row `id=1`), `chat_message_logs`, `activity_logs`, `facebook_channels`, `zalo_channels`, `document_status` | No channel FK, no normalized `conversations/messages` |
| `backend/data/conversations.db` (raw `aiosqlite`) | `conversations(session_id PK, messages JSON)`, `external_conversations(session_id, channel_id, type, ...)`, `external_sync_logs` | **Fragmented** — separate file, JSON blob, not ORM, no `external_message_id` dedup |
| `backend/.chromadb/` | Chroma `PersistentClient` | Correct — keep outside |
| `backend/data/bm25_index/` | Pickled BM25 | Derived — rebuilds |
| `backend/data/uploads/` | Files | Keep |

---

## 4. Single-file redesign — target: `backend/data/app.db` only (single-tenant)

**Principle:** All relational state in **one** `app.db` via SQLAlchemy (`sqlite+aiosqlite`). Derived/non-relational stays out (§7). **No `tenant_id` column anywhere.**

### 4.1 Adaptability matrix — CQA → RAG (single-tenant)

| CQA pattern | Adopt? | Change for single-tenant |
|-------------|--------|--------------------------|
| `tenants` + `user_tenants` (multi-tenant + RBAC) | **Do not adapt** | Single-tenant. Keep `user.role='user'|'admin'` as today. Drop `tenants` and `user_tenants` tables entirely. |
| `channels` (encrypted creds, `is_active`, `last_sync_*`, `metadata`) | **Adapt** | Merge `facebook_channels`+`zalo_channels` → one `channels(channel_type, external_id, credentials_encrypted, ...)`. Unique ` (channel_type, external_id)` (no tenant). |
| `conversations` + `messages` normalized | **Adapt** | Replace JSON blob with `conversations` + `messages`. Unique `(channel_id, external_conversation_id)` and `(conversation_id, external_message_id)`. Enables idempotent FB/Zalo sync. |
| `jobs`/`job_runs`/`job_results` | **Adapt with changes — rename** | RAG needs `ingest_jobs` (doc→chunk→embed). Reuse shape but drop `tenant_id`. Start with ingest only if minimal. |
| `app_settings` KV (`tenant_id, setting_key` unique) | **Adapt** | Replace single-row `ai_settings` → `app_settings(setting_key UNIQUE, value_encrypted/value_plain)`. No tenant prefix. `zalo_webhook_url` global becomes a key. |
| `activity_logs` + `ai_usage_logs` | **Adapt** | Keep `activity_logs`/`chat_message_logs` but drop `tenant_id`. Add `ai_usage_logs(provider,model,input/output_tokens,cost)` — single-tenant. |
| `notification_logs` | **Defer** | Add empty or skip until Telegram/Email needed |
| `oauth_*` | **Do not adapt** | Out of scope |

### 4.2 Target schema (SQLAlchemy — `app.db`, no `tenant_id`)

```python
# app/models/base.py
class Base(DeclarativeBase): pass
def _uuid(): return str(uuid.uuid4())
```

**Users** (keep fastapi-users, no tenant table)

```python
class User(SQLAlchemyBaseUserTableUUID, Base):
    role: Mapped[str] = mapped_column(String(50), default="user")  # user | admin
# No Tenant / UserTenant tables
```

**Channels — replaces `facebook_channels` + `zalo_channels`**

```python
class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    channel_type: Mapped[str] = mapped_column(String(20))  # zalo | facebook
    name: Mapped[str] = mapped_column(String(255))
    external_id: Mapped[str | None] = mapped_column(String(255))
    credentials_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary(2048))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_sync_status: Mapped[str | None] = mapped_column(String(20))
    last_sync_error: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[str | None] = mapped_column(Text)  # json
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    __table_args__ = (UniqueConstraint("channel_type","external_id", name="uq_channel_type_ext"),)
```

**Conversations + messages — replaces `conversations.db`**

```python
class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # session_id
    channel_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("channels.id"), index=True)
    external_conversation_id: Mapped[str | None] = mapped_column(String(255))
    external_user_id: Mapped[str | None] = mapped_column(String(255))
    customer_name: Mapped[str | None] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(500), default="New chat")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    __table_args__ = (UniqueConstraint("channel_id","external_conversation_id", name="uq_conv_channel_ext"),)

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id"), index=True)
    external_message_id: Mapped[str | None] = mapped_column(String(255))
    sender_type: Mapped[str] = mapped_column(String(20))  # customer | agent | system  (RAG: user|assistant|system)
    sender_name: Mapped[str | None] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(50), default="text")
    attachments: Mapped[str | None] = mapped_column(Text)  # json
    sent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    raw_data: Mapped[str | None] = mapped_column(Text)  # json
    # RAG-specific (nullable for channel messages)
    model: Mapped[str | None] = mapped_column(String(128))
    sources: Mapped[str | None] = mapped_column(Text)  # json
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    __table_args__ = (
        UniqueConstraint("conversation_id","external_message_id", name="uq_msg_conv_ext"),
        Index("idx_msg_conv_time", "conversation_id", "sent_at"),
    )
```

`chat_message_logs` → deprecate (migrate into `messages` with `model/sources/tokens`). `chat_sessions` → `conversations` (keep `title/pinned`).

**Documents / chunks** (new)

```python
class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(255), unique=True)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str | None] = mapped_column(String(100))
    byte_size: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="indexed")
    error_message: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    chroma_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

**KV settings — replaces single-row `ai_settings`**

```python
class AppSetting(Base):
    __tablename__ = "app_settings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    setting_key: Mapped[str] = mapped_column(String(255), unique=True)
    value_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary(2048))
    value_plain: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
```

Migrate `ai_settings` → `app_settings` rows (`ai_provider`, `ollama_base_url`, `zalo_webhook_url` plain; `zalo_verify_token`, API keys encrypted).

**Logs**

```python
class ActivityLog(Base):
    __tablename__ = "activity_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(36))
    user_email: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(50), index=True)
    resource_type: Mapped[str | None] = mapped_column(String(50))
    resource_id: Mapped[str | None] = mapped_column(String(100))
    detail: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

class AIUsageLog(Base):
    __tablename__ = "ai_usage_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str | None] = mapped_column(String(36))
    job_run_id: Mapped[str | None] = mapped_column(String(36))
    provider: Mapped[str | None] = mapped_column(String(20))
    model: Mapped[str | None] = mapped_column(String(100))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10,6))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

class SyncLog(Base):
    __tablename__ = "sync_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    channel_id: Mapped[str] = mapped_column(String(36), ForeignKey("channels.id"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    detail: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

No `tenant_id` on any table. If multi-tenant is ever needed, it would be a breaking schema change (intentional — per your single-tenant decision).

### 4.3 Indexes (SQLite, single-tenant)

- `UNIQUE(channel_type, external_id)` on `channels`
- `UNIQUE(channel_id, external_conversation_id)` on `conversations` + `INDEX(last_message_at)`
- `UNIQUE(conversation_id, external_message_id)` on `messages` + `INDEX(conversation_id, sent_at)`
- `UNIQUE(setting_key)` on `app_settings`
- `INDEX(created_at)` + `INDEX(action)` on `activity_logs`; `INDEX(channel_id)` on `sync_logs`

Via SQLAlchemy `UniqueConstraint` / `Index` (mirrors CQA `addUniqueConstraints` pattern).

---

## 5. What stays outside `app.db`

| Store | Keep outside? | Reason |
|-------|---------------|--------|
| `backend/.chromadb/` | **Yes** | Vectors need HNSW, not relational. Reference via `document_chunks.chroma_id`. |
| `backend/data/bm25_index/` | **Yes, derived** | Rebuilt from DB |
| `backend/data/uploads/` | **Yes** | Files on disk; DB stores `documents.title/byte_size/mime_type` |
| `backend/logfire` | **Yes** | Observability side-channel |

---

## 6. Migration plan (single-tenant, idempotent)

1. **Ensure `app.db` schema** — `Base.metadata.create_all()` creates `channels, conversations, messages, app_settings, ai_usage_logs, sync_logs, documents, document_chunks` (no tenants table).
2. **Channels:** `facebook_channels` + `zalo_channels` → `channels`
   ```sql
   INSERT OR IGNORE INTO channels(id, channel_type, name, external_id, credentials_encrypted, is_active, last_sync_at, last_sync_status)
   SELECT id, 'facebook', page_name, page_id, bot_token_encrypted, is_active, last_sync_at, last_sync_status FROM facebook_channels
   UNION ALL
   SELECT id, 'zalo', bot_username, bot_id, bot_token_encrypted, is_active, last_sync_at, last_sync_status FROM zalo_channels;
   ```
3. **Settings:** `ai_settings` (single row) → `app_settings` KV (7-9 rows):
   ```python
   for k in ["ai_provider","ollama_base_url","ollama_model","openai_model","zalo_webhook_url"]:
       insert(setting_key=k, value_plain=v)
   for k in ["ollama_api_key","openai_api_key","zalo_verify_token","zalo_api_key"]:
       insert(setting_key=k, value_encrypted=fernet_encrypt(v))
   ```
   Keep `ai_settings` for rollback; `get_ai_settings()` reads KV first.
4. **Conversations + messages:** `conversations.db:conversations(messages JSON)` + `external_conversations` + `chat_sessions` → `conversations+messages`
   ```python
   for sid, messages_json in conversations_db:
       create_conversation(id=sid, title=chat_sessions.title, channel_id=external_conversations.channel_id, ...)
       for msg in json.loads(messages_json):
           insert messages(conversation_id=sid, sender_type=msg.role, content=..., sent_at=..., external_message_id=msg.id, ...)
   # also migrate chat_message_logs → messages (dedup by content+sent_at)
   ```
5. **Sync logs:** `external_sync_logs` → `sync_logs` (drop `type`/`tenant`).
6. **Switch `conversation_store.py`:** replace raw `aiosqlite` (`conversations.db`) with ORM `app.db` via `async_session_factory`. Dual-read old DB one release, then delete.
7. **Verify:** `SELECT count(*) FROM messages` == `chat_message_logs` + external messages.
8. **Cleanup (next release):** `DROP TABLE ai_settings, chat_sessions, facebook_channels, zalo_channels`; delete `backend/data/conversations.db` + `bm25_index` (regenerates).

---

## 7. File layout after

```
backend/data/app.db          # ONE SQLite file — all relational (single-tenant, no tenant_id)
backend/.chromadb/            # vectors (external)
backend/data/bm25_index/      # derived (regenerates)
backend/data/uploads/         # originals
# deleted: backend/data/conversations.db
```

`app/db/session.py` stays sole engine:
```python
_DB_PATH = _DB_DIR / "app.db"
engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_PATH}")
```
Remove `conversation_store.py:_get_conn()` aiosqlite path.

---

## 8. What NOT to copy from CQA

- **MySQL / GORM** — keep SQLite + SQLAlchemy; CQA `SetMaxOpenConns(100)` is MySQL-specific; SQLite is single-writer + `asyncio.Lock`.
- **Tenants / multi-tenant uniques / permissions JSON** — dropped entirely per single-tenant decision.
- **OAuth tables** — out of scope until MCP.

---

## 9. References

- CQA bootstrap: https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/db/mysql.go
- Models: channel https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/db/models/channel.go, conversation https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/db/models/conversation.go, message https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/db/models/message.go, job https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/db/models/job.go, setting https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/db/models/setting.go, user https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/db/models/user.go, tenant https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/db/models/tenant.go, activity_log https://raw.githubusercontent.com/tanviet12/chat-quality-agent/main/backend/db/models/activity_log.go
- RAG current: `backend/app/db/session.py`, `backend/app/db/conversation_store.py`, `backend/app/models/chat_logging.py`, `backend/app/models/ai_settings.py`, `backend/app/models/session.py`

---

## 10. Next steps

1. Create `app/models/_single_file.py` with `Channel/Conversation/Message/Document/DocumentChunk/AppSetting/AIUsageLog/SyncLog` (no `Tenant`).
2. Generate `scripts/migrate_to_single_db.py` per §6, test on copy of `data/`.
3. Switch `conversation_store.py` to ORM, remove `conversations.db` path, keep Chroma outside.
