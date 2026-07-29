from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.models.schemas import SessionDetail, SessionMessage
from app.models.session import ChatSession
from app.services.rag import get_checkpointer, get_messages

router = APIRouter()


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str, db: AsyncSession = Depends(get_async_session)):
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    raw = await get_messages(session_id)
    messages = [SessionMessage.model_validate(m) for m in raw]
    return SessionDetail(messages=messages)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, db: AsyncSession = Depends(get_async_session)):
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")

    await db.execute(delete(ChatSession).where(ChatSession.id == session_id))
    await db.commit()

    db = await get_checkpointer()
    await db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    await db.commit()
