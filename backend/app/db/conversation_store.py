import asyncio
import logging
from pathlib import Path

import aiosqlite
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

from app.core.config import settings

logger = logging.getLogger(__name__)

_conn: aiosqlite.Connection | None = None


async def _get_conn() -> aiosqlite.Connection:
    global _conn
    if _conn is None:
        db_path = Path(settings.upload_dir).resolve().parent / "conversations.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _conn = await aiosqlite.connect(str(db_path))
        await _conn.execute(
            "CREATE TABLE IF NOT EXISTS conversations ("
            "session_id TEXT PRIMARY KEY, messages TEXT NOT NULL)"
        )
        await _conn.commit()
        logger.info("Conversation store opened at %s", db_path)
    return _conn


async def load_messages(session_id: str) -> list[ModelMessage]:
    conn = await _get_conn()
    cur = await conn.execute(
        "SELECT messages FROM conversations WHERE session_id = ?", (session_id,)
    )
    row = await cur.fetchone()
    await cur.close()
    if row is None:
        return []
    return ModelMessagesTypeAdapter.validate_json(row[0])


async def save_messages(session_id: str, messages: list[ModelMessage]) -> None:
    conn = await _get_conn()
    data = ModelMessagesTypeAdapter.dump_json(messages).decode()
    await conn.execute(
        "INSERT INTO conversations (session_id, messages) VALUES (?, ?) "
        "ON CONFLICT(session_id) DO UPDATE SET messages = excluded.messages",
        (session_id, data),
    )
    await conn.commit()


async def delete_conversation(session_id: str) -> None:
    conn = await _get_conn()
    await conn.execute(
        "DELETE FROM conversations WHERE session_id = ?", (session_id,)
    )
    await conn.commit()


async def close() -> None:
    global _conn
    if _conn is not None:
        await _conn.close()
        _conn = None


def _check() -> None:
    from pydantic_ai.messages import ModelRequest, UserPromptPart

    async def main() -> None:
        await close()
        await save_messages("t", [ModelRequest([UserPromptPart("hi")])])
        loaded = await load_messages("t")
        assert len(loaded) == 1
        assert isinstance(loaded[0].parts[0], UserPromptPart)
        await delete_conversation("t")
        assert await load_messages("t") == []
        await close()

    asyncio.run(main())
    print("conversation_store round-trip OK")


if __name__ == "__main__":
    _check()
