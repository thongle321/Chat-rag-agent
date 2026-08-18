import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.models.schemas import ChatRequest, ChatResponse
from app.models.session import ChatSession
from app.services.rag import answer_question, stream_answer

router = APIRouter()


async def _ensure_session(request: ChatRequest, db: AsyncSession) -> ChatSession:
    session_id = request.session_id

    if session_id:
        result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
        session = result.scalar_one_or_none()
        if session:
            return session

    sid = str(uuid.uuid4())
    session = ChatSession(id=sid, title="New chat")
    db.add(session)
    await db.commit()
    return session


async def _finish_title(session: ChatSession, question: str, db: AsyncSession) -> None:
    if session.title == "New chat":
        session.title = question[:60]

    await db.execute(
        update(ChatSession)
        .where(ChatSession.id == session.id)
        .values(title=session.title, updated_at=datetime.now(UTC).replace(tzinfo=None))
    )
    await db.commit()


@router.post("/query", response_model=ChatResponse)
async def query_chat(request: ChatRequest, db: AsyncSession = Depends(get_async_session)):
    session = await _ensure_session(request, db)
    response = await answer_question(request.question, session_id=session.id)
    await _finish_title(session, request.question, db)
    return response


@router.post("/query/stream")
async def query_chat_stream(request: ChatRequest, db: AsyncSession = Depends(get_async_session)):
    session = await _ensure_session(request, db)
    session_id = session.id

    async def event_stream() -> AsyncIterator[str]:
        async for ev in stream_answer(request.question, session_id):
            if ev["type"] == "text_delta":
                yield f"data: {json.dumps({'content': ev['content']})}\n\n"
            elif ev["type"] == "sources":
                yield f"event: sources\ndata: {json.dumps({'sources': ev['sources']})}\n\n"
            elif ev["type"] == "error":
                detail = json.dumps({"detail": ev["detail"], "status_code": ev["status_code"]})
                yield f"event: error\ndata: {detail}\n\n"
            elif ev["type"] == "done":
                yield f"event: done\ndata: {json.dumps({'session_id': ev['session_id'], 'model': ev['model']})}\n\n"
        await _finish_title(session, request.question, db)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
