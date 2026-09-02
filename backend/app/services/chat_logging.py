"""Helpers to write durable logs to app.db — mirrors CQA backend/db/activity.go:LogActivity."""

from __future__ import annotations

import json
import logging

import logfire

from app.db.session import async_session_factory
from app.models.chat_logging import ActivityLog, ChatMessageLog

logger = logging.getLogger(__name__)


async def log_chat_message(
    *,
    session_id: str,
    role: str,
    content: str,
    user_id: str | None = None,
    user_email: str | None = None,
    model: str | None = None,
    sources: list[dict] | None = None,
    latency_ms: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    ip_address: str | None = None,
) -> str:
    """Insert one ChatMessageLog row. Returns id. Never raises to caller."""
    try:
        async with async_session_factory() as db:
            row = ChatMessageLog(
                session_id=session_id,
                user_id=user_id,
                user_email=user_email,
                role=role,
                content=content,
                model=model,
                sources=json.dumps(sources, ensure_ascii=False) if sources else None,
                latency_ms=latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                ip_address=ip_address,
            )
            db.add(row)
            await db.commit()
            await db.refresh(row)
            # Structured Logfire span attribute — your Logfire token (if set) ships this to Logfire cloud;
            # otherwise it stays in local Logfire handler / stdout. CQA only had log.Printf to stdout + MySQL.
            logfire.info(
                "chat.message logged",
                session_id=session_id,
                role=role,
                model=model or "",
                sources_n=len(sources or []),
                latency_ms=latency_ms or 0,
                user_id=user_id or "",
                user_email=user_email or "",
                prompt_tokens=prompt_tokens or 0,
                completion_tokens=completion_tokens or 0,
            )
            return row.id
    except Exception:
        logger.exception("Failed to write chat_message_log session=%s role=%s", session_id, role)
        return ""


async def log_activity(
    *,
    action: str,
    user_id: str | None = None,
    user_email: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: str | None = None,
    error_message: str | None = None,
    ip_address: str | None = None,
) -> str:
    """Insert one ActivityLog row — mirrors CQA LogActivity(tenantID, userID, ...)."""
    try:
        async with async_session_factory() as db:
            row = ActivityLog(
                user_id=user_id,
                user_email=user_email,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                detail=detail,
                error_message=error_message,
                ip_address=ip_address,
            )
            db.add(row)
            await db.commit()
            await db.refresh(row)
            logfire.info(
                "activity",
                action=action,
                resource_type=resource_type or "",
                resource_id=resource_id or "",
                user_id=user_id or "",
            )
            return row.id
    except Exception:
        logger.exception("Failed to write activity_log action=%s", action)
        return ""


def _client_ip(request) -> str | None:
    if request is None:
        return None
    # Respect X-Forwarded-For when behind Nginx (like CQA docker/nginx.conf proxy)
    xff = request.headers.get("x-forwarded-for") if hasattr(request, "headers") else None
    if xff:
        return xff.split(",")[0].strip()[:45]
    client = getattr(request, "client", None)
    if client and getattr(client, "host", None):
        return str(client.host)[:45]
    return None
