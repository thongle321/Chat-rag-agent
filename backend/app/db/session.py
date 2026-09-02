from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.user import Base, User

# Resolve absolute path for SQLite DB
_DB_DIR = Path(settings.upload_dir).resolve().parent  # data/
_DB_DIR.mkdir(parents=True, exist_ok=True)
_DB_PATH = _DB_DIR / "app.db"

engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_PATH}")
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def create_db_and_tables():
    """Create all tables (idempotent) and run single-file migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # idempotent migrations into unified tables (no tenant_id, single-tenant)
    try:
        await _run_single_file_migrations()
    except Exception:
        import logging

        logging.getLogger(__name__).exception("single-file migration failed (non-fatal)")


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Generic DB session dependency for non-user operations."""
    async with async_session_factory() as session:
        yield session


async def get_user_db() -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
    """Dependency that yields a SQLAlchemyUserDatabase for fastapi-users."""
    async with async_session_factory() as session:
        yield SQLAlchemyUserDatabase(session, User)


async def _run_single_file_migrations() -> None:  # noqa: C901 — idempotent, many branches
    """One-time idempotent migration into single-file unified tables (no tenant_id)."""
    import json as _json
    import logging

    from sqlalchemy import text as _text

    logger = logging.getLogger(__name__)

    async with async_session_factory() as session:
        # 1) ai_settings (single-row id=1) -> app_settings KV (unique setting_key)
        try:
            res = await session.execute(_text("SELECT ai_provider, ollama_base_url, ollama_model, ollama_api_key, openai_model, openai_api_key, zalo_api_key, zalo_verify_token, zalo_webhook_url FROM ai_settings WHERE id=1"))
            row = res.fetchone()
            if row:
                cols = ["ai_provider", "ollama_base_url", "ollama_model", "ollama_api_key", "openai_model", "openai_api_key", "zalo_api_key", "zalo_verify_token", "zalo_webhook_url"]
                # app_settings.value_encrypted is LargeBinary, value_plain is Text
                # Reuse ai_settings encryption helper so decrypt round-trips
                from app.services.ai_settings import _decrypt as _dec, _encrypt as _enc  # lazy import

                for k, v in zip(cols, row, strict=True):
                    if v is None:
                        continue
                    # check exists
                    exists = await session.execute(_text("SELECT 1 FROM app_settings WHERE setting_key=:k"), {"k": k})
                    if exists.fetchone():
                        continue
                    # _dec expects ciphertext; plain values were encrypted in ai_settings row
                    # so we decrypt then re-store via same scheme (value_encrypted for _API_KEY_FIELDS)
                    is_encrypted = k in {"ollama_api_key", "openai_api_key", "zalo_api_key", "zalo_verify_token"}
                    if is_encrypted:
                        plain = _dec(v) if v else ""
                        if not plain:
                            continue
                        enc = _enc(plain)
                        await session.execute(
                            _text("INSERT OR IGNORE INTO app_settings (id, setting_key, value_encrypted) VALUES (:id, :k, :v)"),
                            {"id": __import__("uuid").uuid4().hex[:36], "k": k, "v": enc.encode() if isinstance(enc, str) else enc},
                        )
                    else:
                        if not v:
                            continue
                        await session.execute(
                            _text("INSERT OR IGNORE INTO app_settings (id, setting_key, value_plain) VALUES (:id, :k, :v)"),
                            {"id": __import__("uuid").uuid4().hex[:36], "k": k, "v": str(v)},
                        )
                await session.commit()
        except Exception as e:
            await session.rollback()
            logger.debug("app_settings migration skipped: %s", e)

        # 2) facebook_channels / zalo_channels -> channels (single table, no tenant)
        for src_table, ch_type in [("facebook_channels", "facebook"), ("zalo_channels", "zalo")]:
            try:
                res = await session.execute(_text(f"SELECT id, page_id, bot_id, page_name, bot_username, page_token, bot_token, slug, is_active, last_sync_at, last_sync_status FROM {src_table} LIMIT 1000"))
            except Exception:
                # table may not exist or different schema — try minimal
                try:
                    res = await session.execute(_text(f"SELECT * FROM {src_table} LIMIT 1"))
                    # generic fallback — just count
                    res = await session.execute(_text(f"SELECT id FROM {src_table} LIMIT 1000"))
                except Exception:
                    continue
            try:
                # Re-query with correct columns per type
                if ch_type == "facebook":
                    rows = (await session.execute(_text("SELECT id, page_id, page_name, page_token, slug, is_active, last_sync_at, last_sync_status, last_sync_error FROM facebook_channels"))).fetchall()
                    for r in rows:
                        _id, _ext, _name, _tok, _slug, _active, _lsat, _lsst, _lserr = r
                        exists = await session.execute(_text("SELECT 1 FROM channels WHERE id=:id OR (channel_type=:t AND external_id=:e)"), {"id": _id, "t": ch_type, "e": _ext})
                        if exists.fetchone():
                            continue
                        enc = _tok.encode() if _tok else None
                        # store token as encrypted blob via ai_settings helper for consistency
                        if _tok:
                            try:
                                from app.services.ai_settings import _encrypt as _enc2

                                enc = _enc2(_tok).encode()
                            except Exception:
                                enc = _tok.encode()
                        await session.execute(
                            _text("INSERT OR IGNORE INTO channels (id, channel_type, name, external_id, credentials_encrypted, slug, is_active, last_sync_status) VALUES (:id,:t,:n,:e,:c,:s,:a,:ls)"),
                            {"id": _id, "t": ch_type, "n": _name or _ext or "", "e": _ext, "c": enc, "s": _slug, "a": 1 if _active else 0, "ls": _lsst},
                        )
                else:
                    rows = (await session.execute(_text("SELECT id, bot_id, bot_username, bot_token, slug, is_active, last_sync_at, last_sync_status, last_sync_error, verify_token, webhook_url FROM zalo_channels"))).fetchall()
                    for r in rows:
                        _id, _bid, _bname, _btok, _slug, _active, _lsat, _lsst, _lserr, _vt, _wh = r
                        exists = await session.execute(_text("SELECT 1 FROM channels WHERE id=:id OR (channel_type=:t AND external_id=:e)"), {"id": _id, "t": ch_type, "e": _bid})
                        if exists.fetchone():
                            continue
                        enc = None
                        if _btok:
                            try:
                                from app.services.ai_settings import _encrypt as _enc3

                                enc = _enc3(_btok).encode()
                            except Exception:
                                enc = _btok.encode()
                        meta = _json.dumps({"verify_token": _vt or "", "webhook_url": _wh or ""}) if (_vt or _wh) else None
                        await session.execute(
                            _text("INSERT OR IGNORE INTO channels (id, channel_type, name, external_id, credentials_encrypted, slug, is_active, last_sync_status, metadata_json) VALUES (:id,:t,:n,:e,:c,:s,:a,:ls,:m)"),
                            {"id": _id, "t": ch_type, "n": _bname or _bid or "", "e": _bid, "c": enc, "s": _slug, "a": 1 if _active else 0, "ls": _lsst, "m": meta},
                        )
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.debug("channels migration skipped for %s: %s", ch_type, e)

        # 3) document_status -> documents (title=filename)
        try:
            rows = (await session.execute(_text("SELECT filename, status, chunk_count, error_message FROM document_status"))).fetchall()
            for _fn, _st, _cc, _err in rows:
                exists = await session.execute(_text("SELECT 1 FROM documents WHERE title=:t"), {"t": _fn})
                if exists.fetchone():
                    continue
                await session.execute(
                    _text("INSERT OR IGNORE INTO documents (id, title, original_filename, status, chunk_count, error_message) VALUES (:id,:t,:o,:s,:c,:e)"),
                    {"id": __import__("uuid").uuid4().hex[:36], "t": _fn, "o": _fn, "s": _st or "indexed", "c": _cc or 0, "e": _err},
                )
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.debug("documents migration skipped: %s", e)

        # 4) conversations.db (external file) -> conversations/messages/sync_logs (only if file exists)
        try:
            conv_db = Path(settings.upload_dir).resolve().parent / "conversations.db"
            if conv_db.exists():
                import aiosqlite as _aiosqlite

                async with _aiosqlite.connect(str(conv_db)) as c:
                    # sync logs
                    try:
                        cur = await c.execute("SELECT id, channel_id, type, status, detail, error_message, created_at FROM external_sync_logs")
                        srows = await cur.fetchall()
                        for _sid, _cid, _typ, _st, _det, _err, _cat in srows:
                            # map to channels.id if possible (external_id match) else keep channel_id as-is
                            exists = await session.execute(_text("SELECT 1 FROM sync_logs WHERE id=:id"), {"id": _sid})
                            if exists.fetchone():
                                continue
                            # resolve channel_id to channels.id if external_id matches
                            ch = await session.execute(_text("SELECT id FROM channels WHERE external_id=:e LIMIT 1"), {"e": _cid})
                            crow = ch.fetchone()
                            real_cid = crow[0] if crow else _cid
                            # skip if channel_id not in channels (FK) — insert only if resolvable or create placeholder
                            if not crow:
                                continue
                            await session.execute(
                                _text("INSERT OR IGNORE INTO sync_logs (id, channel_id, status, detail, error_message, created_at) VALUES (:id,:cid,:s,:d,:e,:c)"),
                                {"id": _sid, "cid": real_cid, "s": _st or "success", "d": _det, "e": _err, "c": _cat or __import__("datetime").datetime.utcnow().isoformat()},
                            )
                    except Exception as e:
                        logger.debug("sync_logs migration skipped: %s", e)
                    # conversations + messages: only covers channel-linked sessions; keep it best-effort
                    try:
                        cur = await c.execute("SELECT session_id, channel_id, type, username, updated_at FROM external_conversations")
                        erows = await cur.fetchall()
                        for _sid, _cid, _typ, _uname, _up in erows:
                            exists = await session.execute(_text("SELECT 1 FROM conversations WHERE id=:id"), {"id": _sid})
                            if exists.fetchone():
                                continue
                            ch = await session.execute(_text("SELECT id FROM channels WHERE external_id=:e LIMIT 1"), {"e": _cid})
                            crow = ch.fetchone()
                            real_cid = crow[0] if crow else None
                            await session.execute(
                                _text("INSERT OR IGNORE INTO conversations (id, channel_id, external_conversation_id, customer_name, title, last_message_at) VALUES (:id,:cid,:ext,:cust,:tit,:lm)"),
                                {"id": _sid, "cid": real_cid, "ext": _sid, "cust": _uname, "tit": _uname or "Chat", "lm": _up},
                            )
                        cur2 = await c.execute("SELECT session_id, messages FROM conversations")
                        mrows = await cur2.fetchall()
                        for _sid, _msgs in mrows:
                            try:
                                arr = _json.loads(_msgs) if _msgs else []
                            except Exception:
                                continue
                            for m in arr[-50:]:  # cap per conversation to avoid blowup
                                # pydantic-ai ModelMessage shape varies; try to extract role/content
                                role = m.get("role") or m.get("kind") or "user"
                                # normalize
                                if role not in ("user", "assistant", "system", "customer", "agent"):
                                    role = "user" if role == "user" else "assistant"
                                if role == "agent":
                                    role = "assistant"
                                if role == "customer":
                                    role = "user"
                                content = ""
                                if isinstance(m.get("content"), str):
                                    content = m["content"]
                                elif isinstance(m.get("parts"), list):
                                    content = " ".join(str(p.get("content") or p.get("text") or "") for p in m["parts"])
                                elif isinstance(m.get("content"), list):
                                    content = " ".join(str(p.get("text") or "") for p in m["content"])
                                if not content:
                                    continue
                                # dedup by conversation_id + content+sent_at would need hash; just insert with random id
                                await session.execute(
                                    _text("INSERT OR IGNORE INTO messages (id, conversation_id, sender_type, content, content_type, sent_at) VALUES (:id,:cid,:st,:c,:ct,:sa)"),
                                    {"id": __import__("uuid").uuid4().hex[:36], "cid": _sid, "st": role, "c": content[:4000], "ct": "text", "sa": __import__("datetime").datetime.utcnow().isoformat()},
                                )
                    except Exception as e:
                        logger.debug("conversations/messages migration skipped: %s", e)
                await session.commit()
        except Exception as e:
            await session.rollback()
            logger.debug("conversations.db migration skipped: %s", e)
