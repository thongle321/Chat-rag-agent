import asyncio
import logging
import uuid
from pathlib import Path

import aiosqlite
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

from app.core.config import settings

logger = logging.getLogger(__name__)

# ponytail: uncapped for full history sync 18 Jul -> now; cap at 1000 if storage grows
_MAX_STORED_MESSAGES = 1000

_conn: aiosqlite.Connection | None = None
_lock = asyncio.Lock()


async def _get_conn() -> aiosqlite.Connection:
    global _conn
    if _conn is not None:
        return _conn
    async with _lock:
        if _conn is None:
            db_path = Path(settings.upload_dir).resolve().parent / "conversations.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            _conn = await aiosqlite.connect(str(db_path))
            await _conn.execute(
                "CREATE TABLE IF NOT EXISTS conversations (session_id TEXT PRIMARY KEY, messages TEXT NOT NULL)"
            )
            await _conn.execute(
                "CREATE TABLE IF NOT EXISTS external_conversations ("
                "session_id TEXT PRIMARY KEY, channel_id TEXT NOT NULL, type TEXT NOT NULL, username TEXT, updated_at TEXT NOT NULL)"
            )
            await _conn.execute("CREATE INDEX IF NOT EXISTS idx_external_conv_type_channel ON external_conversations(type, channel_id)")
            await _conn.execute(
                "CREATE TABLE IF NOT EXISTS external_sync_logs ("
                "id TEXT PRIMARY KEY, channel_id TEXT NOT NULL, type TEXT NOT NULL, status TEXT NOT NULL, detail TEXT, error_message TEXT, created_at TEXT NOT NULL)"
            )
            await _conn.execute("CREATE INDEX IF NOT EXISTS idx_external_sync_type_channel ON external_sync_logs(type, channel_id)")
            # fresh DB — drop old facebook_* tables if present
            try:
                await _conn.execute("DROP TABLE IF EXISTS facebook_conversation_links")
                await _conn.execute("DROP TABLE IF EXISTS facebook_sync_logs")
            except Exception:
                pass
            await _conn.commit()
            logger.info("Conversation store opened at %s", db_path)
    return _conn


async def link_page_to_session(
    session_id: str, page_id: str, username: str | None = None, updated_at: str | None = None, channel_type: str = "facebook"
) -> None:
    conn = await _get_conn()
    await conn.execute(
        "INSERT INTO external_conversations (session_id, channel_id, type, username, updated_at) VALUES (?, ?, ?, ?, COALESCE(?, datetime('now'))) "
        "ON CONFLICT(session_id) DO UPDATE SET channel_id=excluded.channel_id, type=excluded.type, username=COALESCE(excluded.username, username), updated_at=excluded.updated_at",
        (session_id, page_id, channel_type, username, updated_at),
    )
    await conn.commit()


async def list_sessions_by_page(page_id: str, limit: int = 20, offset: int = 0, channel_type: str = "facebook") -> list[str]:
    conn = await _get_conn()
    cur = await conn.execute(
        "SELECT session_id FROM external_conversations WHERE channel_id=? AND type=? AND session_id NOT LIKE 'fbconv_%' ORDER BY updated_at DESC LIMIT ? OFFSET ?",
        (page_id, channel_type, limit, offset),
    )
    rows = await cur.fetchall()
    await cur.close()
    return [r[0] for r in rows]


async def list_sessions_with_meta(page_id: str, limit: int | None = None, offset: int = 0, channel_type: str = "facebook") -> list[dict]:
    conn = await _get_conn()
    if limit is None:
        cur = await conn.execute(
            "SELECT session_id, username, updated_at FROM external_conversations WHERE channel_id=? AND type=? AND session_id NOT LIKE 'fbconv_%' ORDER BY updated_at DESC",
            (page_id, channel_type),
        )
    else:
        cur = await conn.execute(
            "SELECT session_id, username, updated_at FROM external_conversations WHERE channel_id=? AND type=? AND session_id NOT LIKE 'fbconv_%' ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (page_id, channel_type, limit, offset),
        )
    rows = await cur.fetchall()
    await cur.close()
    return [{"session_id": r[0], "username": r[1], "updated_at": r[2]} for r in rows]


async def count_sessions_by_page(page_id: str, channel_type: str = "facebook") -> int:
    conn = await _get_conn()
    cur = await conn.execute(
        "SELECT COUNT(*) FROM external_conversations WHERE channel_id=? AND type=? AND session_id NOT LIKE 'fbconv_%'",
        (page_id, channel_type),
    )
    row = await cur.fetchone()
    await cur.close()
    return row[0] if row else 0


async def cleanup_placeholder_sessions(page_id: str | None = None, channel_type: str = "facebook") -> int:
    conn = await _get_conn()
    if page_id:
        cur = await conn.execute(
            "DELETE FROM external_conversations WHERE session_id LIKE 'fbconv_%' AND channel_id=? AND type=?", (page_id, channel_type)
        )
    else:
        cur = await conn.execute("DELETE FROM external_conversations WHERE session_id LIKE 'fbconv_%' AND type=?", (channel_type,))
    await conn.commit()
    return cur.rowcount if cur else 0


async def add_sync_log(page_id: str, status: str, detail: str = "", error_message: str | None = None, channel_type: str = "facebook") -> None:
    conn = await _get_conn()
    await conn.execute(
        "INSERT INTO external_sync_logs (id, channel_id, type, status, detail, error_message, created_at) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
        (str(uuid.uuid4()), page_id, channel_type, status, detail, error_message),
    )
    await conn.commit()


async def list_sync_logs(page_id: str, limit: int = 10, offset: int = 0, channel_type: str = "facebook") -> list[dict]:
    conn = await _get_conn()
    cur = await conn.execute(
        "SELECT id, status, detail, error_message, created_at FROM external_sync_logs WHERE channel_id=? AND type=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (page_id, channel_type, limit, offset),
    )
    rows = await cur.fetchall()
    await cur.close()
    return [{"id": r[0], "status": r[1], "detail": r[2], "error_message": r[3], "created_at": r[4]} for r in rows]


async def delete_sync_logs_by_page(page_id: str, channel_type: str = "facebook") -> int:
    conn = await _get_conn()
    cur = await conn.execute("DELETE FROM external_sync_logs WHERE channel_id=? AND type=?", (page_id, channel_type))
    await conn.commit()
    return cur.rowcount if cur else 0


async def load_messages(session_id: str) -> list[ModelMessage]:
    conn = await _get_conn()
    cur = await conn.execute("SELECT messages FROM conversations WHERE session_id = ?", (session_id,))
    row = await cur.fetchone()
    await cur.close()
    if row is None:
        return []
    return ModelMessagesTypeAdapter.validate_json(row[0])


async def save_messages(session_id: str, messages: list[ModelMessage]) -> None:
    conn = await _get_conn()
    messages = messages[-_MAX_STORED_MESSAGES:]
    data = ModelMessagesTypeAdapter.dump_json(messages).decode()
    await conn.execute(
        "INSERT INTO conversations (session_id, messages) VALUES (?, ?) "
        "ON CONFLICT(session_id) DO UPDATE SET messages = excluded.messages",
        (session_id, data),
    )
    await conn.commit()


async def delete_conversation(session_id: str) -> None:
    conn = await _get_conn()
    await conn.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
    await conn.commit()


async def close() -> None:
    global _conn
    if _conn is not None:
        await _conn.close()
        _conn = None
