"""Prod log readers — mirrors CQA GET /activity-logs and GET /conversations/messages."""

import json
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.models.chat_logging import ActivityLog, ChatMessageLog
from app.models.user import User
from app.services.user_manager import current_active_user

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()[:45]
    if request.client and request.client.host:
        return str(request.client.host)[:45]
    return None


@router.get("/chat-logs")
async def list_chat_logs(
    request: Request,
    session_id: str | None = Query(None),
    role: Literal["user", "assistant"] | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_session),
    user: User = current_active_user,
):
    """Paginated per-message chat logs — durable prod log (app.db). Admin/user scoped."""
    q = select(ChatMessageLog).order_by(ChatMessageLog.created_at.desc())
    count_q = select(func.count()).select_from(ChatMessageLog)
    if session_id:
        q = q.where(ChatMessageLog.session_id == session_id)
        count_q = count_q.where(ChatMessageLog.session_id == session_id)
    if role:
        q = q.where(ChatMessageLog.role == role)
        count_q = count_q.where(ChatMessageLog.role == role)
    # Non-admins only see own logs (if user_id was captured); admins see all
    is_admin = getattr(user, "role", None) == "admin" or getattr(user, "is_superuser", False)
    if not is_admin:
        uid = str(user.id)
        q = q.where((ChatMessageLog.user_id == uid) | (ChatMessageLog.user_id.is_(None)))
        count_q = count_q.where((ChatMessageLog.user_id == uid) | (ChatMessageLog.user_id.is_(None)))

    total = (await db.execute(count_q)).scalar_one()
    rows = (await db.execute(q.offset((page - 1) * per_page).limit(per_page))).scalars().all()

    def _fmt(r: ChatMessageLog) -> dict:
        try:
            sources = json.loads(r.sources) if r.sources else None
        except Exception:
            sources = None
        return {
            "id": r.id,
            "session_id": r.session_id,
            "user_id": r.user_id,
            "user_email": r.user_email,
            "role": r.role,
            "content": r.content,
            "model": r.model,
            "sources": sources,
            "latency_ms": r.latency_ms,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "ip_address": r.ip_address,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }

    return {"total": total, "page": page, "per_page": per_page, "items": [_fmt(r) for r in rows]}


@router.get("/activity-logs")
async def list_activity_logs(
    request: Request,
    action: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_session),
    user: User = current_active_user,
):
    """Paginated activity audit — mirrors CQA GET /activity-logs?page&per_page&action."""
    is_admin = getattr(user, "role", None) == "admin" or getattr(user, "is_superuser", False)
    q = select(ActivityLog).order_by(ActivityLog.created_at.desc())
    count_q = select(func.count()).select_from(ActivityLog)
    if action:
        q = q.where(ActivityLog.action.like(f"{action}%"))
        count_q = count_q.where(ActivityLog.action.like(f"{action}%"))
    if not is_admin:
        uid = str(user.id)
        q = q.where(ActivityLog.user_id == uid)
        count_q = count_q.where(ActivityLog.user_id == uid)

    total = (await db.execute(count_q)).scalar_one()
    rows = (await db.execute(q.offset((page - 1) * per_page).limit(per_page))).scalars().all()
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "user_email": r.user_email,
                "action": r.action,
                "resource_type": r.resource_type,
                "resource_id": r.resource_id,
                "detail": r.detail,
                "error_message": r.error_message,
                "ip_address": r.ip_address,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }
