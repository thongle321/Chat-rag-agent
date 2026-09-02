"""Unified conversation store — single-tenant, single file (app.db).

Replaces the old dual-file raw aiosqlite `conversations.db` (conversations JSON blob
+ external_conversations + external_sync_logs) with ORM tables in app.db:
  - conversations (id=session_id, channel_id, title, last_message_at, ...)
  - messages (conversation_id FK, sender_type, content, raw_data JSON)
  - sync_logs (channel_id FK, status, detail)

All functions keep the same signatures as before so callers (rag.py, facebook/zalo)
do not change. Dual-read fallback: if app.db has no rows for a session, it will
try the legacy conversations.db file once (then migrate on next save).

No tenant_id — single tenant.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path

import aiosqlite
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

_MAX_STORED_MESSAGES = 1000

_legacy_path = Path(settings.upload_dir).resolve().parent / "conversations.db"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _extract_text_and_role(msg: ModelMessage) -> tuple[str, str]:
    """Best-effort extract (role, text) from a pydantic-ai ModelMessage."""
    # ModelMessage is a union; inspect via model_dump
    try:
        d = msg.model_dump() if hasattr(msg, "model_dump") else {}
    except Exception:
        d = {}
    role = d.get("role") or d.get("kind") or "user"
    if role not in ("user", "assistant", "system"):
        # map from ModelRequest/ModelResponse kinds
        if "request" in str(type(msg)).lower():
            role = "user"
        else:
            role = "assistant"
    # content extraction
    content = ""
    if isinstance(d.get("content"), str):
        content = d["content"]
    elif isinstance(d.get("parts"), list):
        parts = d["parts"]
        chunks: list[str] = []
        for p in parts:
            if isinstance(p, dict):
                chunks.append(str(p.get("content") or p.get("text") or ""))
            else:
                chunks.append(str(p))
        content = " ".join(chunks).strip()
    elif isinstance(d.get("content"), list):
        chunks = []
        for p in d["content"]:
            if isinstance(p, dict):
                chunks.append(str(p.get("text") or ""))
        content = " ".join(chunks).strip()
    if not content:
        # fallback to string representation
        try:
            content = str(msg)
        except Exception:
            content = ""
    return role, content[:8000]


async def _ensure_conversation(session: AsyncSession, session_id: str, channel_id: str | None = None) -> None:
    from app.models.unified import Conversation

    res = await session.execute(select(Conversation).where(Conversation.id == session_id))
    if res.scalar_one_or_none() is None:
        conv = Conversation(id=session_id, channel_id=channel_id, title="New chat")
        session.add(conv)
        await session.flush()


# ---------------------------------------------------------------------------
# public API — keep signatures compatible
# ---------------------------------------------------------------------------
async def link_page_to_session(
    session_id: str, page_id: str, username: str | None = None, updated_at: str | None = None, channel_type: str = "facebook"
) -> None:
    """Link a FB/Zalo page/bot to a session → conversations.channel_id + customer_name."""
    try:
        from app.models.unified import Channel, Conversation

        async with async_session_factory() as s:
            # resolve channel by external_id + type
            ch_id: str | None = None
            res = await s.execute(select(Channel.id).where(Channel.external_id == page_id, Channel.channel_type == channel_type))
            row = res.fetchone()
            if row:
                ch_id = row[0]
            else:
                # create placeholder channel if not exists (so FK holds)
                # try to find any channel of this type, else create
                ch_id = page_id  # fallback: use page_id as id if channels table empty
                exists = await s.execute(select(Channel).where(Channel.id == ch_id))
                if exists.scalar_one_or_none() is None:
                    # create placeholder
                    ch = Channel(id=ch_id, channel_type=channel_type, name=username or page_id, external_id=page_id, is_active=True)
                    s.add(ch)
                    await s.flush()
            await _ensure_conversation(s, session_id, ch_id)
            # update conversation metadata
            await s.execute(
                update(Conversation)
                .where(Conversation.id == session_id)
                .values(
                    channel_id=ch_id,
                    customer_name=username or Conversation.customer_name,
                    external_conversation_id=session_id,
                )
            )
            await s.commit()
    except Exception:
        logger.exception("link_page_to_session failed for %s", session_id)


async def list_sessions_by_page(page_id: str, limit: int = 20, offset: int = 0, channel_type: str = "facebook") -> list[str]:
    try:
        from app.models.unified import Channel, Conversation

        async with async_session_factory() as s:
            # resolve channel
            res = await s.execute(select(Channel.id).where(Channel.external_id == page_id, Channel.channel_type == channel_type))
            row = res.fetchone()
            ch_id = row[0] if row else page_id
            q = (
                select(Conversation.id)
                .where(Conversation.channel_id == ch_id)
                .order_by(Conversation.last_message_at.desc().nulls_last(), Conversation.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = (await s.execute(q)).fetchall()
            if rows:
                return [r[0] for r in rows]
            # fallback: also match external_conversation
            q2 = (
                select(Conversation.id)
                .where(Conversation.external_conversation_id == page_id)
                .limit(limit)
                .offset(offset)
            )
            rows2 = (await s.execute(q2)).fetchall()
            return [r[0] for r in rows2]
    except Exception:
        logger.exception("list_sessions_by_page failed")
        return []


async def list_sessions_with_meta(page_id: str, limit: int | None = None, offset: int = 0, channel_type: str = "facebook") -> list[dict]:
    try:
        from app.models.unified import Channel, Conversation

        async with async_session_factory() as s:
            res = await s.execute(select(Channel.id).where(Channel.external_id == page_id, Channel.channel_type == channel_type))
            row = res.fetchone()
            ch_id = row[0] if row else page_id
            q = select(Conversation.id, Conversation.customer_name, Conversation.updated_at).where(Conversation.channel_id == ch_id).order_by(Conversation.last_message_at.desc().nulls_last(), Conversation.updated_at.desc())
            if limit is not None:
                q = q.limit(limit).offset(offset)
            rows = (await s.execute(q)).fetchall()
            return [{"session_id": r[0], "username": r[1], "updated_at": r[2].isoformat() if r[2] else None} for r in rows]
    except Exception:
        logger.exception("list_sessions_with_meta failed")
        return []


async def count_sessions_by_page(page_id: str, channel_type: str = "facebook") -> int:
    try:
        from app.models.unified import Channel, Conversation
        from sqlalchemy import func

        async with async_session_factory() as s:
            res = await s.execute(select(Channel.id).where(Channel.external_id == page_id, Channel.channel_type == channel_type))
            row = res.fetchone()
            ch_id = row[0] if row else page_id
            cnt = await s.execute(select(func.count()).select_from(Conversation).where(Conversation.channel_id == ch_id))
            return int(cnt.scalar() or 0)
    except Exception:
        return 0


async def cleanup_placeholder_sessions(page_id: str | None = None, channel_type: str = "facebook") -> int:
    # placeholder sessions were fbconv_* in legacy DB — now just delete conversations with placeholder prefix
    try:
        from app.models.unified import Conversation

        async with async_session_factory() as s:
            if page_id:
                res = await s.execute(delete(Conversation).where(Conversation.id.like("fbconv_%")))
            else:
                res = await s.execute(delete(Conversation).where(Conversation.id.like("fbconv_%")))
            await s.commit()
            return res.rowcount or 0
    except Exception:
        return 0


async def add_sync_log(page_id: str, status: str, detail: str = "", error_message: str | None = None, channel_type: str = "facebook") -> None:
    try:
        from app.models.unified import Channel, SyncLog

        async with async_session_factory() as s:
            res = await s.execute(select(Channel.id).where(Channel.external_id == page_id, Channel.channel_type == channel_type))
            row = res.fetchone()
            ch_id = row[0] if row else None
            if not ch_id:
                # create placeholder channel so FK holds
                ch_id = page_id
                exists = await s.execute(select(Channel).where(Channel.id == ch_id))
                if exists.scalar_one_or_none() is None:
                    s.add(Channel(id=ch_id, channel_type=channel_type, name=page_id, external_id=page_id))
                    await s.flush()
            log = SyncLog(id=str(uuid.uuid4()), channel_id=ch_id, status=status, detail=detail, error_message=error_message)
            s.add(log)
            # update channel last_sync
            await s.execute(
                update(Channel).where(Channel.id == ch_id).values(last_sync_status=status, last_sync_at=text("CURRENT_TIMESTAMP"))
            )
            await s.commit()
    except Exception:
        logger.exception("add_sync_log failed")


async def list_sync_logs(page_id: str, limit: int = 10, offset: int = 0, channel_type: str = "facebook") -> list[dict]:
    try:
        from app.models.unified import Channel, SyncLog

        async with async_session_factory() as s:
            res = await s.execute(select(Channel.id).where(Channel.external_id == page_id, Channel.channel_type == channel_type))
            row = res.fetchone()
            ch_id = row[0] if row else page_id
            q = select(SyncLog.id, SyncLog.status, SyncLog.detail, SyncLog.error_message, SyncLog.created_at).where(SyncLog.channel_id == ch_id).order_by(SyncLog.created_at.desc()).limit(limit).offset(offset)
            rows = (await s.execute(q)).fetchall()
            return [{"id": r[0], "status": r[1], "detail": r[2], "error_message": r[3], "created_at": r[4].isoformat() if r[4] else None} for r in rows]
    except Exception:
        logger.exception("list_sync_logs failed")
        return []


async def delete_sync_logs_by_page(page_id: str, channel_type: str = "facebook") -> int:
    try:
        from app.models.unified import Channel, SyncLog

        async with async_session_factory() as s:
            res = await s.execute(select(Channel.id).where(Channel.external_id == page_id, Channel.channel_type == channel_type))
            row = res.fetchone()
            ch_id = row[0] if row else page_id
            res2 = await s.execute(delete(SyncLog).where(SyncLog.channel_id == ch_id))
            await s.commit()
            return res2.rowcount or 0
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# messages — pydantic-ai history stored normalized (one row per ModelMessage,
# raw_data holds JSON of that single message so we can round-trip via
# ModelMessagesTypeAdapter).
# ---------------------------------------------------------------------------
async def load_messages(session_id: str) -> list[ModelMessage]:
    # 1) try unified messages table
    try:
        from app.models.unified import Message

        async with async_session_factory() as s:
            res = await s.execute(
                select(Message.raw_data, Message.content, Message.sender_type).where(Message.conversation_id == session_id).order_by(Message.sent_at, Message.created_at)
            )
            rows = res.fetchall()
            if rows:
                # Prefer raw_data round-trip if present
                raw_datas = [r[0] for r in rows if r[0]]
                if raw_datas and len(raw_datas) == len(rows):
                    # raw_datas are JSON strings of single ModelMessages — rebuild array
                    try:
                        arr_json = "[" + ",".join(raw_datas) + "]"
                        return ModelMessagesTypeAdapter.validate_json(arr_json)
                    except Exception:
                        logger.debug("raw_data round-trip failed, falling back to content rows")
                # Fallback: rows have content but no raw_data (legacy migration) — return empty so rag rebuilds?
                # We return empty list; rag will treat as new conversation and re-query.
                # To preserve history, we could synthesize ModelMessages, but pydantic-ai expects proper parts.
                # For now, try to synthesize via raw_data fallback is above; otherwise return empty.
                if raw_datas:
                    try:
                        arr_json = "[" + ",".join(raw_datas) + "]"
                        return ModelMessagesTypeAdapter.validate_json(arr_json)
                    except Exception:
                        pass
                # If we have content rows but no raw_data, we cannot reconstruct ModelMessage safely — return empty
                # (caller will start fresh; durable audit is still in messages table)
                return []
    except Exception:
        logger.exception("load_messages (unified) failed for %s", session_id)

    # 2) fallback: legacy conversations.db file (dual-read, one release)
    if _legacy_path.exists():
        try:
            async with aiosqlite.connect(str(_legacy_path)) as conn:
                cur = await conn.execute("SELECT messages FROM conversations WHERE session_id = ?", (session_id,))
                row = await cur.fetchone()
                await cur.close()
                if row is not None:
                    return ModelMessagesTypeAdapter.validate_json(row[0])
        except Exception:
            logger.debug("legacy load_messages fallback failed for %s", session_id)
    return []


async def save_messages(session_id: str, messages: list[ModelMessage]) -> None:
    messages = messages[-_MAX_STORED_MESSAGES:]
    # Serialize each ModelMessage individually into raw_data
    raw_datas: list[str] = []
    metas: list[tuple[str, str]] = []  # (role, content)
    for m in messages:
        try:
            # dump single message as array of 1 then peel
            j = ModelMessagesTypeAdapter.dump_json([m]).decode()
            arr = json.loads(j)
            raw = json.dumps(arr[0]) if arr else json.dumps({})
        except Exception:
            raw = json.dumps({})
        raw_datas.append(raw)
        try:
            role, content = _extract_text_and_role(m)
        except Exception:
            role, content = "user", ""
        metas.append((role, content))

    try:
        from app.models.unified import Conversation, Message

        async with async_session_factory() as s:
            await _ensure_conversation(s, session_id)
            # replace all messages for this conversation (simple, idempotent)
            await s.execute(delete(Message).where(Message.conversation_id == session_id))
            await s.flush()
            for (role, content), raw in zip(metas, raw_datas, strict=True):
                # map role to sender_type
                sender_type = role if role in ("user", "assistant", "system") else "user"
                msg = Message(
                    id=str(uuid.uuid4()),
                    conversation_id=session_id,
                    sender_type=sender_type,
                    content=content or "",
                    content_type="text",
                    raw_data=raw,
                )
                s.add(msg)
            # update conversation counters
            await s.execute(
                update(Conversation)
                .where(Conversation.id == session_id)
                .values(message_count=len(messages), last_message_at=text("CURRENT_TIMESTAMP"))
            )
            await s.commit()
    except Exception:
        logger.exception("save_messages (unified) failed for %s", session_id)
        # fallback: try legacy file so we don't lose history entirely
        if _legacy_path.exists():
            try:
                async with aiosqlite.connect(str(_legacy_path)) as conn:
                    data = ModelMessagesTypeAdapter.dump_json(messages).decode()
                    await conn.execute(
                        "INSERT INTO conversations (session_id, messages) VALUES (?, ?) ON CONFLICT(session_id) DO UPDATE SET messages = excluded.messages",
                        (session_id, data),
                    )
                    await conn.commit()
            except Exception:
                logger.exception("legacy save_messages fallback failed for %s", session_id)


async def delete_conversation(session_id: str) -> None:
    try:
        from app.models.unified import Conversation, Message

        async with async_session_factory() as s:
            await s.execute(delete(Message).where(Message.conversation_id == session_id))
            await s.execute(delete(Conversation).where(Conversation.id == session_id))
            await s.commit()
    except Exception:
        logger.exception("delete_conversation failed for %s", session_id)
    # also clean legacy file
    if _legacy_path.exists():
        try:
            async with aiosqlite.connect(str(_legacy_path)) as conn:
                await conn.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
                await conn.execute("DELETE FROM external_conversations WHERE session_id = ?", (session_id,))
                await conn.commit()
        except Exception:
            pass


async def close() -> None:
    # unified store uses async_session_factory (engine), not a persistent aiosqlite conn
    # kept for compatibility with app/main.py lifespan
    return
