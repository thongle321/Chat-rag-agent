import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_async_session
from app.models.schemas import ChatRequest, ChatResponse
from app.models.session import ChatSession
from app.models.user import User
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


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()[:45]
    if request.client and request.client.host:
        return str(request.client.host)[:45]
    return None


def _get_jwt_secret() -> str:
    s = settings.jwt_secret_key
    return s.get_secret_value() if hasattr(s, "get_secret_value") else str(s)


def _decode_bearer(request: Request) -> dict | None:
    """Decode the Bearer token without enforcing auth — single helper for both callers."""
    try:
        # Starlette headers are case-insensitive — one lookup is enough.
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return None
        token = auth[7:].strip()
        if not token:
            return None
        return jwt.decode(token, _get_jwt_secret(), algorithms=["HS256"], options={"verify_exp": False})
    except Exception:
        return None


def _user_id_from_payload(payload: dict | None) -> str | None:
    if not payload:
        return None
    sub = payload.get("sub")
    return str(sub) if sub else None


def _optional_user_id(request: Request) -> str | None:
    """Best-effort user_id from Bearer token without enforcing auth — keeps chat open."""
    return _user_id_from_payload(_decode_bearer(request))


async def _optional_user_with_email(request: Request, db: AsyncSession) -> tuple[str | None, str | None]:
    """Return (user_id, user_email) best-effort — mirrors CQA activity_logs user_email."""
    payload = _decode_bearer(request)  # decode once, reuse for sub + email fallback
    uid = _user_id_from_payload(payload)
    if not uid:
        return None, None
    try:
        # User.id is UUID — cast string uid to UUID for comparison (otherwise SELECT returns None)
        try:
            uid_uuid = uuid.UUID(uid)
        except Exception:
            uid_uuid = uid  # fallback to string comparison
        result = await db.execute(select(User).where(User.id == uid_uuid))
        user = result.scalar_one_or_none()
        if user:
            return str(user.id), user.email
        # Fallback: token contained email claim directly
        return uid, payload.get("email") if payload else None
    except Exception:
        return uid, None


@router.post("/query", response_model=ChatResponse)
async def query_chat(
    request: ChatRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_async_session),
):
    # Allow anonymous like ChatGPT — best-effort auth for logging
    user_id, user_email = await _optional_user_with_email(http_request, db)
    session = await _ensure_session(request, db)
    ip = _client_ip(http_request)
    response = await answer_question(
        request.question, session_id=session.id, user_id=user_id, user_email=user_email, ip_address=ip
    )
    await _finish_title(session, request.question, db)
    return response


# Single dispatch for stream events → SSE frames (answer_question folds the same
# events to a final answer; formatting lives here so the cascade exists once).
_SSE_FIELDS: dict[str, tuple[str | None, tuple[str, ...]]] = {
    "text_delta": (None, ("content",)),
    "sources": ("sources", ("sources",)),
    "products": ("products", ("products",)),
    "followups": ("followups", ("followups",)),
    "error": ("error", ("detail", "status_code")),
    "done": ("done", ("session_id", "model")),
}


def _format_sse(ev: dict) -> str | None:
    spec = _SSE_FIELDS.get(ev["type"])
    if spec is None:
        return None
    event, fields = spec
    # Tolerant on purpose: never break the SSE stream on a malformed event.
    # All producers (_error_event, stream_answer) always include every listed key.
    data = json.dumps({k: ev[k] for k in fields if k in ev})
    return f"event: {event}\ndata: {data}\n\n" if event else f"data: {data}\n\n"


@router.post("/query/stream")
async def query_chat_stream(request: ChatRequest, http_request: Request, db: AsyncSession = Depends(get_async_session)):
    session = await _ensure_session(request, db)
    session_id = session.id
    user_id, user_email = await _optional_user_with_email(http_request, db)
    ip = _client_ip(http_request)

    async def event_stream() -> AsyncIterator[str]:
        async for ev in stream_answer(
            request.question, session_id, user_id=user_id, user_email=user_email, ip_address=ip
        ):
            frame = _format_sse(ev)
            if frame is not None:
                yield frame
        await _finish_title(session, request.question, db)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
