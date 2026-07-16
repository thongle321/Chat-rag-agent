from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, not_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.models.schemas import SessionDetail, SessionInfo, SessionMessage, TitleUpdate
from app.models.session import ChatSession
from app.services.rag import get_checkpointer, get_messages

router = APIRouter()


@router.get("/sessions", response_model=list[SessionInfo])
async def list_sessions(db: AsyncSession = Depends(get_async_session)):
    result = await db.execute(
        select(ChatSession).order_by(ChatSession.pinned.desc(), ChatSession.updated_at.desc())
    )
    sessions = result.scalars().all()
    out = []
    for s in sessions:
        msgs = await get_messages(s.id)
        out.append(SessionInfo(
            id=s.id,
            title=s.title,
            message_count=len(msgs),
            pinned=s.pinned,
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat(),
        ))
    return out


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str, db: AsyncSession = Depends(get_async_session)):
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    raw = await get_messages(session_id)
    messages = [SessionMessage(**m) for m in raw]
    return SessionDetail(
        session=SessionInfo(
            id=s.id,
            title=s.title,
            message_count=len(messages),
            pinned=s.pinned,
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat(),
        ),
        messages=messages,
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, db: AsyncSession = Depends(get_async_session)):
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")

    await db.execute(delete(ChatSession).where(ChatSession.id == session_id))
    await db.commit()

    cp = await get_checkpointer()
    await cp.adelete_thread(session_id)


@router.put("/sessions/{session_id}/pin", status_code=204)
async def toggle_pin(session_id: str, db: AsyncSession = Depends(get_async_session)):
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.execute(
        update(ChatSession)
        .where(ChatSession.id == session_id)
        .values(pinned=not_(ChatSession.pinned))
    )
    await db.commit()


@router.put("/sessions/{session_id}/title", response_model=SessionInfo)
async def update_title(session_id: str, body: TitleUpdate, db: AsyncSession = Depends(get_async_session)):
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    await db.execute(
        update(ChatSession).where(ChatSession.id == session_id).values(title=body.title)
    )
    await db.commit()

    msgs = await get_messages(session_id)
    return SessionInfo(
        id=s.id,
        title=body.title,
        message_count=len(msgs),
        pinned=s.pinned,
        created_at=s.created_at.isoformat(),
        updated_at=s.updated_at.isoformat(),
    )
