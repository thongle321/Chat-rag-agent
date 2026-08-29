import asyncio
import logging
from pathlib import Path

import aiosqlite
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

from app.core.config import settings

logger = logging.getLogger(__name__)

# ponytail: keeps stored blob from growing unbounded per session (~10 turns, matches rag._MAX_HISTORY)
_MAX_STORED_MESSAGES = 20

_conn: aiosqlite.Connection | None = None
_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


async def _get_conn() -> aiosqlite.Connection:
    global _conn
    if _conn is not None:
        return _conn
    async with _get_lock():
        if _conn is None:
            db_path = Path(settings.upload_dir).resolve().parent / "conversations.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            _conn = await aiosqlite.connect(str(db_path))
            await _conn.execute(
                "CREATE TABLE IF NOT EXISTS conversations (session_id TEXT PRIMARY KEY, messages TEXT NOT NULL)"
            )
            await _conn.execute(
                "CREATE TABLE IF NOT EXISTS facebook_conversation_links ("
                "session_id TEXT PRIMARY KEY, page_id TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            # ponytail: add username column for display (FB participant name)
            try:
                await _conn.execute("ALTER TABLE facebook_conversation_links ADD COLUMN username TEXT")
            except Exception:
                pass
            await _conn.execute(
                "CREATE TABLE IF NOT EXISTS facebook_sync_logs ("
                "id TEXT PRIMARY KEY, page_id TEXT NOT NULL, status TEXT NOT NULL, detail TEXT, error_message TEXT, created_at TEXT NOT NULL)"
            )
            await _conn.commit()
            logger.info("Conversation store opened at %s", db_path)
    return _conn


async def link_page_to_session(
    session_id: str, page_id: str, username: str | None = None, updated_at: str | None = None
) -> None:
    conn = await _get_conn()
    await conn.execute(
        "INSERT INTO facebook_conversation_links (session_id, page_id, username, updated_at) VALUES (?, ?, ?, COALESCE(?, datetime('now'))) "
        "ON CONFLICT(session_id) DO UPDATE SET page_id=excluded.page_id, username=COALESCE(excluded.username, username), updated_at=excluded.updated_at",
        (session_id, page_id, username, updated_at),
    )
    await conn.commit()


async def list_sessions_by_page(page_id: str, limit: int = 20, offset: int = 0) -> list[str]:
    conn = await _get_conn()
    cur = await conn.execute(
        "SELECT session_id FROM facebook_conversation_links WHERE page_id=? AND session_id NOT LIKE 'fbconv_%' ORDER BY updated_at DESC LIMIT ? OFFSET ?",
        (page_id, limit, offset),
    )
    rows = await cur.fetchall()
    await cur.close()
    return [r[0] for r in rows]


async def list_sessions_with_meta(page_id: str, limit: int = 20, offset: int = 0) -> list[dict]:
    conn = await _get_conn()
    cur = await conn.execute(
        "SELECT session_id, username, updated_at FROM facebook_conversation_links WHERE page_id=? AND session_id NOT LIKE 'fbconv_%' ORDER BY updated_at DESC LIMIT ? OFFSET ?",
        (page_id, limit, offset),
    )
    rows = await cur.fetchall()
    await cur.close()
    return [{"session_id": r[0], "username": r[1], "updated_at": r[2]} for r in rows]


async def count_sessions_by_page(page_id: str) -> int:
    conn = await _get_conn()
    cur = await conn.execute(
        "SELECT COUNT(*) FROM facebook_conversation_links WHERE page_id=? AND session_id NOT LIKE 'fbconv_%'",
        (page_id,),
    )
    row = await cur.fetchone()
    await cur.close()
    return row[0] if row else 0


async def cleanup_placeholder_sessions(page_id: str | None = None) -> int:
    conn = await _get_conn()
    if page_id:
        cur = await conn.execute(
            "DELETE FROM facebook_conversation_links WHERE session_id LIKE 'fbconv_%' AND page_id=?", (page_id,)
        )
    else:
        cur = await conn.execute("DELETE FROM facebook_conversation_links WHERE session_id LIKE 'fbconv_%'")
    await conn.commit()
    return cur.rowcount if cur else 0


async def purge_conversations_by_page(page_id: str) -> int:
    conn = await _get_conn()
    cur = await conn.execute("SELECT session_id FROM facebook_conversation_links WHERE page_id=?", (page_id,))
    rows = await cur.fetchall()
    await cur.close()
    count = 0
    for r in rows:
        sid = r[0]
        await conn.execute("DELETE FROM conversations WHERE session_id=?", (sid,))
        count += 1
    await conn.execute("DELETE FROM facebook_conversation_links WHERE page_id=?", (page_id,))
    await conn.commit()
    return count


async def add_sync_log(page_id: str, status: str, detail: str = "", error_message: str | None = None) -> None:
    import uuid

    conn = await _get_conn()
    await conn.execute(
        "INSERT INTO facebook_sync_logs (id, page_id, status, detail, error_message, created_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
        (str(uuid.uuid4()), page_id, status, detail, error_message),
    )
    await conn.commit()


async def list_sync_logs(page_id: str, limit: int = 10, offset: int = 0) -> list[dict]:
    conn = await _get_conn()
    cur = await conn.execute(
        "SELECT id, status, detail, error_message, created_at FROM facebook_sync_logs WHERE page_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (page_id, limit, offset),
    )
    rows = await cur.fetchall()
    await cur.close()
    return [{"id": r[0], "status": r[1], "detail": r[2], "error_message": r[3], "created_at": r[4]} for r in rows]


async def delete_sync_logs_by_page(page_id: str) -> int:
    conn = await _get_conn()
    cur = await conn.execute("DELETE FROM facebook_sync_logs WHERE page_id=?", (page_id,))
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
