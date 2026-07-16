from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.models.schemas import ChatRequest, ChatResponse
from app.models.session import ChatSession
from app.services.rag import answer_question

router = APIRouter()


@router.post("/query", response_model=ChatResponse)
async def query_chat(request: ChatRequest, db: AsyncSession = Depends(get_async_session)):
    session_id = request.session_id

    if session_id:
        result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
        session = result.scalar_one_or_none()
        if not session:
            session_id = None

    if not session_id:
        from langchain_core.utils.uuid import uuid7
        sid = str(uuid7())
        session = ChatSession(id=sid, title="Cuộc hội thoại mới")
        db.add(session)
        await db.commit()
        session_id = sid

    response = await answer_question(request.question, session_id=session_id)

    if session.title == "Cuộc hội thoại mới":
        session.title = request.question[:60]

    await db.execute(
        update(ChatSession)
        .where(ChatSession.id == session_id)
        .values(title=session.title, updated_at=datetime.utcnow())
    )
    await db.commit()

    return response
