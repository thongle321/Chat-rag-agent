from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.conversation_store import delete_conversation
from app.db.session import get_async_session
from app.models.schemas import SessionDetail, SessionMessage
from app.models.session import ChatSession
from app.models.user import User
from app.services.chat_logging import log_activity
from app.services.rag import get_messages
from app.services.user_manager import current_active_user, current_user_user

router = APIRouter()


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str, db: AsyncSession = Depends(get_async_session), user: User = current_user_user):
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    s = result.scalar_one_or_none()
    if not s:
        # Allow Facebook PSID sessions without ChatSession row (facebook_conversation_links)
        try:
            raw_check = await get_messages(session_id)
            if not raw_check:
                raise HTTPException(status_code=404, detail="Session not found")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc

    raw = await get_messages(session_id)
    messages = [SessionMessage.model_validate(m) for m in raw]
    return SessionDetail(messages=messages)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    user: User = current_user_user,
):
    await db.execute(delete(ChatSession).where(ChatSession.id == session_id))
    await db.commit()
    await delete_conversation(session_id)
    ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()[:45]
        if request.headers.get("x-forwarded-for")
        else (str(request.client.host)[:45] if request.client else None)
    )
    await log_activity(
        action="session.delete",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="session",
        resource_id=session_id,
        ip_address=ip,
    )
