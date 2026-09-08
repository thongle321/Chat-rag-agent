"""Prod log readers — mirrors CQA GET /activity-logs and GET /conversations/messages."""

import json
from datetime import date, datetime, time, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.models.chat_logging import ActivityLog, ChatMessageLog
from app.models.unified import AIUsageLog
from app.models.user import User
from app.services.user_manager import current_active_user, current_admin_user

# Fixed FX for the cost table (agreed 26,000 VND per USD).
USD_TO_VND = 26000

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()[:45]
    if request.client and request.client.host:
        return str(request.client.host)[:45]
    return None


@router.get("/usage/summary")
async def usage_summary(
    provider: Literal["openai", "ollama"] | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: AsyncSession = Depends(get_async_session),
    user: User = current_admin_user,
):
    """Filter-matching totals for the usage page stat cards — same filters as /usage."""
    q = select(
        func.count(),
        func.coalesce(func.sum(AIUsageLog.input_tokens), 0),
        func.coalesce(func.sum(AIUsageLog.output_tokens), 0),
        func.coalesce(func.sum(AIUsageLog.cost_usd), 0),
    ).select_from(AIUsageLog)
    if provider:
        q = q.where(AIUsageLog.provider == provider)
    if date_from:
        q = q.where(AIUsageLog.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        q = q.where(AIUsageLog.created_at < datetime.combine(date_to + timedelta(days=1), time.min))
    turns, input_tokens, output_tokens, cost_usd = (await db.execute(q)).one()
    cost_usd = float(cost_usd)
    return {
        "turns": turns,
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "cost_usd": cost_usd,
        "cost_vnd": cost_usd * USD_TO_VND,
    }


@router.get("/usage")
async def list_usage(
    provider: Literal["openai", "ollama"] | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_session),
    user: User = current_admin_user,
):
    """Paginated per-turn AI usage + cost — admin only (rows carry no user_id)."""
    q = select(AIUsageLog).order_by(AIUsageLog.created_at.desc())
    count_q = select(func.count()).select_from(AIUsageLog)
    if provider:
        q = q.where(AIUsageLog.provider == provider)
        count_q = count_q.where(AIUsageLog.provider == provider)
    if date_from:
        start = datetime.combine(date_from, time.min)
        q = q.where(AIUsageLog.created_at >= start)
        count_q = count_q.where(AIUsageLog.created_at >= start)
    if date_to:
        end = datetime.combine(date_to + timedelta(days=1), time.min)
        q = q.where(AIUsageLog.created_at < end)
        count_q = count_q.where(AIUsageLog.created_at < end)

    total = (await db.execute(count_q)).scalar_one()
    rows = (await db.execute(q.offset((page - 1) * per_page).limit(per_page))).scalars().all()
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [
            {
                "id": r.id,
                "provider": r.provider,
                "model": r.model,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "cost_usd": float(r.cost_usd) if r.cost_usd is not None else None,
                "cost_vnd": float(r.cost_usd * USD_TO_VND) if r.cost_usd is not None else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


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
