import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from httpx import AsyncClient
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.models.user import User
from app.services.facebook_channels import (
    create_channel,
    delete_channel,
    get_channel,
    get_channel_by_page_id,
    get_channel_by_slug,
    list_channels,
    update_channel,
)
from app.services.facebook_config import (
    delete_facebook_config,
    get_facebook_config,
    save_facebook_config,
)
from app.services.rag import answer_question
from app.services.user_manager import current_active_user

logger = logging.getLogger(__name__)

FB_GRAPH_API = "https://graph.facebook.com/v25.0"

_client: AsyncClient | None = None


def _get_client() -> AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = AsyncClient(timeout=30)
    return _client

async def close_client() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None

async def send_message(page_id: str, page_token: str, recipient_id: str, text: str) -> bool:
    url = f"{FB_GRAPH_API}/{page_id}/messages"
    params = {"access_token": page_token}
    payload = {
        "messaging_type": "RESPONSE",
        "recipient": {"id": recipient_id},
        "message": {"text": text},
    }
    resp = await _get_client().post(url, params=params, json=payload)
    if resp.status_code != 200:
        logger.error("Facebook send failed: %s %s", resp.status_code, resp.text)
        return False
    logger.info("Facebook message sent to %s", recipient_id)
    return True

async def mark_seen(page_id: str, page_token: str, recipient_id: str) -> None:
    url = f"{FB_GRAPH_API}/{page_id}/messages"
    params = {"access_token": page_token}
    payload = {
        "recipient": {"id": recipient_id},
        "sender_action": "mark_seen",
    }
    await _get_client().post(url, params=params, json=payload)

async def typing_on(page_id: str, page_token: str, recipient_id: str) -> None:
    url = f"{FB_GRAPH_API}/{page_id}/messages"
    params = {"access_token": page_token}
    payload = {
        "recipient": {"id": recipient_id},
        "sender_action": "typing_on",
    }
    await _get_client().post(url, params=params, json=payload)


async def _health_check(page_id: str, page_token: str) -> dict:
    # ponytail: probe permission-light endpoint first (/{page_id} needs pages_read_engagement)
    for url in [f"{FB_GRAPH_API}/me", f"{FB_GRAPH_API}/{page_id}"]:
        resp = await _get_client().get(url, params={
            "fields": "id,name",
            "access_token": page_token,
        })
        data = resp.json()
        if resp.status_code == 200 and "error" not in data:
            return {"ok": True, "page_name": data.get("name", ""), "page_id": data.get("id", page_id)}
        err = data.get("error", {}) if isinstance(data, dict) else {}
        msg = err.get("message", resp.text[:300]) if err else resp.text[:300]
        code = err.get("code")
        # Friendly hint for the common (#100) review wall — manual paste path, re-gen token with permission
        if code == 100 or "pages_read_engagement" in msg:
            return {
                "ok": False,
                "error": (
                    "Token lacks pages_read_engagement or Page not accessible in current app mode. "
                    "Re-generate your Page Access Token in Graph Explorer with pages_read_engagement checked, "
                    "then paste again. Original: " + msg[:200]
                ),
            }
        if url.endswith("/me"):
            continue
        return {"ok": False, "error": msg}
    return {"ok": False, "error": "Health check failed"}


async def _sync_fetch_conversations(page_id: str, page_token: str, limit: int = 20) -> tuple[int, int, str | None]:
    """Pull like tanviet12: FetchRecentConversations + FetchMessages with real PSID sessions."""
    try:
        resp = await _get_client().get(f"{FB_GRAPH_API}/{page_id}/conversations", params={
            "fields": "id,updated_time,participants",
            "limit": min(limit, 50),
            "access_token": page_token,
        })
        data = resp.json()
        if resp.status_code != 200 or "error" in data:
            err = data.get("error", {}).get("message", resp.text[:200]) if isinstance(data, dict) else resp.text[:200]
            return 0, 0, err
        convs = data.get("data", []) if isinstance(data.get("data"), list) else []
        # Persist real PSID sessions from participants + messages
        msg_count = 0
        try:
            from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

            from app.db.conversation_store import link_page_to_session
            from app.db.conversation_store import save_messages as save_conv_messages

            for c in convs:
                # Extract customer PSID + name from participants (non-page)
                customer_id = None
                customer_name = None
                parts = c.get("participants", {}).get("data", [])
                if isinstance(parts, list):
                    for p in parts:
                        if isinstance(p, dict) and p.get("id") != page_id:
                            customer_id = p.get("id")
                            customer_name = p.get("name")
                            break
                if not customer_id:
                    continue
                fb_updated = c.get("updated_time")
                await link_page_to_session(customer_id, page_id, username=customer_name, updated_at=fb_updated)
                # Fetch recent messages for this conversation to seed AI view
                try:
                    mr = await _get_client().get(f"{FB_GRAPH_API}/{c.get('id')}/messages", params={
                        "fields": "id,message,from,created_time",
                        "limit": 10,
                        "access_token": page_token,
                    })
                    mdata = mr.json()
                    if mr.status_code == 200 and isinstance(mdata.get("data"), list):
                        msgs = list(reversed(mdata["data"]))  # oldest first
                        if msgs:
                            msg_count += len(msgs)
                            # Build minimal ModelMessages for preview (oldest 10)
                            from app.db.conversation_store import load_messages

                            existing = await load_messages(customer_id)
                            # Only seed if no history yet
                            if not existing:
                                conv_msgs = []
                                for m in msgs:
                                    txt = m.get("message") or ""
                                    if not txt:
                                        continue
                                    frm = m.get("from", {}).get("id")
                                    if frm == page_id:
                                        conv_msgs.append(ModelResponse(parts=[TextPart(content=txt)]))
                                    else:
                                        conv_msgs.append(ModelRequest(parts=[UserPromptPart(content=txt)]))
                                if conv_msgs:
                                    await save_conv_messages(customer_id, conv_msgs)
                except Exception:
                    continue
            # Cleanup old placeholders
            try:
                from app.db.conversation_store import cleanup_placeholder_sessions

                await cleanup_placeholder_sessions(page_id)
            except Exception:
                pass
        except Exception:
            pass
        return len(convs), msg_count, None
    except Exception as e:
        return 0, 0, str(e)[:200]


class FacebookChannelRequest(BaseModel):
    page_id: str
    page_name: str
    page_token: str
    verify_token: str
    sync_interval: int | None = 15


class FacebookChannelUpdateRequest(BaseModel):
    page_name: str | None = None
    page_token: str | None = None
    verify_token: str | None = None
    sync_interval: int | None = None
    is_active: bool | None = None


router = APIRouter()


# ---------------------------------------------------------------------------
# Legacy single Config (deprecated id=1) — kept for migration compat
# ---------------------------------------------------------------------------

class FacebookConfigRequest(BaseModel):
    page_id: str
    page_name: str
    page_token: str
    verify_token: str
    sync_interval: int | None = 15


class FacebookConfigResponse(BaseModel):
    page_id: str
    page_name: str
    has_token: bool
    verify_token: str
    sync_interval: int = 15
    last_sync_status: str | None = None
    last_sync_at: str | None = None
    created_at: str | None = None


class FacebookChannelResponse(BaseModel):
    id: str
    page_id: str
    page_name: str
    has_token: bool
    verify_token: str
    sync_interval: int = 15
    last_sync_status: str | None = None
    last_sync_at: str | None = None
    created_at: str | None = None
    is_active: bool = True
    total_conversations: int = 0
    slug: str | None = None


def _channel_to_response(ch: dict) -> FacebookChannelResponse:
    return FacebookChannelResponse(
        id=ch["id"],
        page_id=ch["page_id"],
        page_name=ch.get("page_name", "Facebook Page"),
        has_token=bool(ch.get("page_token")),
        verify_token=ch.get("verify_token", ""),
        sync_interval=ch.get("sync_interval", 15),
        last_sync_status=ch.get("last_sync_status"),
        last_sync_at=ch.get("last_sync_at"),
        created_at=ch.get("created_at"),
        is_active=bool(ch.get("is_active", True)),
        total_conversations=ch.get("total_conversations", 0),
        slug=ch.get("slug"),
    )


# ---------------------------------------------------------------------------
# Config endpoints
# ---------------------------------------------------------------------------

@router.get("/config", response_model=FacebookConfigResponse)
async def get_config(user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    config = await get_facebook_config(db)
    if not config:
        raise HTTPException(status_code=404, detail="No Facebook config found")

    return FacebookConfigResponse(
        page_id=config["page_id"],
        page_name=config.get("page_name", "Facebook Page"),
        has_token=bool(config.get("page_token")),
        verify_token=config.get("verify_token", ""),
        sync_interval=config.get("sync_interval", 15),
        last_sync_status=config.get("last_sync_status"),
        last_sync_at=config.get("last_sync_at"),
        created_at=config.get("created_at"),
    )


@router.post("/config", response_model=FacebookConfigResponse)
async def save_config(
    req: FacebookConfigRequest,
    user: User = current_active_user,
    db: AsyncSession = Depends(get_async_session),
):
    if req.sync_interval is not None and req.sync_interval not in [1, 5, 10, 15, 30, 60, 360, 1440]:
        raise HTTPException(status_code=400, detail="Invalid sync_interval")
    config = await save_facebook_config(
        db, req.page_id, req.verify_token, page_token=req.page_token, page_name=req.page_name,
        sync_interval=req.sync_interval,
    )

    return FacebookConfigResponse(
        page_id=config["page_id"],
        page_name=config.get("page_name", "Facebook Page"),
        has_token=bool(config.get("page_token")),
        verify_token=config["verify_token"],
        sync_interval=config.get("sync_interval", 15),
        last_sync_status=config.get("last_sync_status"),
        last_sync_at=config.get("last_sync_at"),
        created_at=config.get("created_at"),
    )


@router.delete("/config")
async def delete_config(user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    deleted = await delete_facebook_config(db)
    if not deleted:
        # Also try channels
        channels = await list_channels(db)
        if channels:
            raise HTTPException(status_code=400, detail="Multi-channel mode: DELETE /channels/{id} instead")
        raise HTTPException(status_code=404, detail="No Facebook config found")
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Channels CRUD — unlimited pages (primary, ponytail: replaces single id=1)
# ---------------------------------------------------------------------------


@router.get("/channels", response_model=list[FacebookChannelResponse])
async def list_facebook_channels(user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    channels = await list_channels(db)
    # Fallback to legacy id=1 if channels empty for compat
    if not channels:
        legacy = await get_facebook_config(db)
        if legacy:
            channels = [dict(id="legacy-1", **legacy, is_active=True)]
            # normalize legacy id
            channels[0]["id"] = "legacy-1"
    # Attach total_conversations per page_id (Facebook-only)
    try:
        from app.db.conversation_store import count_sessions_by_page

        for c in channels:
            try:
                c["total_conversations"] = await count_sessions_by_page(c["page_id"])
            except Exception:
                c["total_conversations"] = 0
    except Exception:
        pass
    return [_channel_to_response(c) if "has_token" not in c else _channel_to_response(c) for c in channels]


@router.post("/channels", response_model=FacebookChannelResponse)
async def create_facebook_channel(
    req: FacebookChannelRequest, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)
):
    if req.sync_interval is not None and req.sync_interval not in [1, 5, 10, 15, 30, 60, 360, 1440]:
        raise HTTPException(status_code=400, detail="Invalid sync_interval")
    # Real DB create - sync_files removed, default False kept in DB for compat
    ch = await create_channel(db, req.page_id, req.page_name, req.page_token, req.verify_token, req.sync_interval or 15, False)
    try:
        from app.db.conversation_store import count_sessions_by_page

        ch["total_conversations"] = await count_sessions_by_page(ch["page_id"])
    except Exception:
        pass
    return _channel_to_response(ch)


@router.get("/channels/by-page/{page_id}", response_model=FacebookChannelResponse)
async def get_facebook_channel_by_page(page_id: str, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    ch = await get_channel_by_page_id(db, page_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    try:
        from app.db.conversation_store import count_sessions_by_page

        ch["total_conversations"] = await count_sessions_by_page(page_id)
    except Exception:
        pass
    return _channel_to_response(ch)


@router.get("/channels/by-slug/{slug}", response_model=FacebookChannelResponse)
async def get_facebook_channel_by_slug(slug: str, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    ch = await get_channel_by_slug(db, slug)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    try:
        from app.db.conversation_store import count_sessions_by_page

        ch["total_conversations"] = await count_sessions_by_page(ch["page_id"])
    except Exception:
        pass
    return _channel_to_response(ch)


@router.get("/channels/{channel_id}", response_model=FacebookChannelResponse)
async def get_facebook_channel(channel_id: str, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    ch = await get_channel(db, channel_id)
    if not ch:
        # Fallback: try page_id then slug for direct /channels/{identifier} without prefix (good practice)
        ch = await get_channel_by_page_id(db, channel_id)
        if not ch:
            from app.services.facebook_channels import get_channel_by_slug

            ch = await get_channel_by_slug(db, channel_id)
    if not ch:
        if channel_id == "legacy-1":
            legacy = await get_facebook_config(db)
            if legacy:
                ch = dict(id="legacy-1", **legacy, is_active=True)
                try:
                    from app.db.conversation_store import count_sessions_by_page

                    ch["total_conversations"] = await count_sessions_by_page(ch["page_id"])
                except Exception:
                    pass
                return _channel_to_response(ch)
        raise HTTPException(status_code=404, detail="Channel not found")
    try:
        from app.db.conversation_store import count_sessions_by_page

        ch["total_conversations"] = await count_sessions_by_page(ch["page_id"])
    except Exception:
        pass
    return _channel_to_response(ch)


@router.put("/channels/{channel_id}", response_model=FacebookChannelResponse)
async def update_facebook_channel(
    channel_id: str, req: FacebookChannelUpdateRequest, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)
):
    if req.sync_interval is not None and req.sync_interval not in [1, 5, 10, 15, 30, 60, 360, 1440]:
        raise HTTPException(status_code=400, detail="Invalid sync_interval")
    if channel_id == "legacy-1":
        # Migrate legacy to new channel on first update
        legacy = await get_facebook_config(db)
        if not legacy:
            raise HTTPException(status_code=404, detail="Channel not found")
        ch = await create_channel(
            db,
            legacy["page_id"],
            req.page_name or legacy["page_name"],
            req.page_token or legacy["page_token"],
            req.verify_token or legacy["verify_token"],
            req.sync_interval or legacy.get("sync_interval", 15),
            False,
        )
        try:
            from app.db.conversation_store import count_sessions_by_page

            ch["total_conversations"] = await count_sessions_by_page(ch["page_id"])
        except Exception:
            pass
        return _channel_to_response(ch)
    # sync_files removed — keep existing DB value, ignore request
    ch = await update_channel(db, channel_id, req.page_name, req.page_token, req.verify_token, req.sync_interval, None, req.is_active)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    try:
        from app.db.conversation_store import count_sessions_by_page

        ch["total_conversations"] = await count_sessions_by_page(ch["page_id"])
    except Exception:
        pass
    return _channel_to_response(ch)


@router.delete("/channels/{channel_id}")
async def delete_facebook_channel(channel_id: str, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    if channel_id == "legacy-1":
        ok = await delete_facebook_config(db)
        if not ok:
            raise HTTPException(status_code=404, detail="Channel not found")
        return {"status": "deleted"}
    ok = await delete_channel(db, channel_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Channel not found")
    return {"status": "deleted"}


@router.get("/channels/by-page/{page_id}/health")
async def channel_health_by_page(page_id: str, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    ch = await get_channel_by_page_id(db, page_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    result = await _health_check(ch["page_id"], ch["page_token"])
    if result.get("ok"):
        from sqlalchemy import text as _text

        try:
            await db.execute(_text("UPDATE facebook_channels SET last_sync_status='success', last_sync_at=datetime('now') WHERE page_id=:pid"), {"pid": page_id})
            await db.commit()
        except Exception:
            await db.rollback()
    return result


@router.get("/channels/by-slug/{slug}/health")
async def channel_health_by_slug(slug: str, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    from app.services.facebook_channels import get_channel_by_slug

    ch = await get_channel_by_slug(db, slug)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    result = await _health_check(ch["page_id"], ch["page_token"])
    if result.get("ok"):
        from sqlalchemy import text as _text

        try:
            await db.execute(_text("UPDATE facebook_channels SET last_sync_status='success', last_sync_at=datetime('now') WHERE slug=:slug"), {"slug": slug})
            await db.commit()
        except Exception:
            await db.rollback()
    return result


@router.get("/channels/{channel_id}/health")
async def channel_health(channel_id: str, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    ch = await get_channel(db, channel_id)
    if not ch:
        ch = await get_channel_by_page_id(db, channel_id)
    if not ch and channel_id == "legacy-1":
        ch = await get_facebook_config(db)
        if ch:
            ch = dict(id="legacy-1", **ch)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    result = await _health_check(ch["page_id"], ch["page_token"])
    if result.get("ok"):
        from sqlalchemy import text as _text

        try:
            await db.execute(_text("UPDATE facebook_channels SET last_sync_status='success', last_sync_at=datetime('now') WHERE id=:id"), {"id": channel_id})
            await db.commit()
        except Exception:
            await db.rollback()
    return result


@router.post("/channels/by-page/{page_id}/sync")
async def channel_sync_by_page(page_id: str, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    ch = await get_channel_by_page_id(db, page_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    result = await _health_check(ch["page_id"], ch["page_token"])
    status = "success" if result.get("ok") else "error"
    detail = ""
    if result.get("ok"):
        # Best practice pull like tanviet12: conversations + messages count (history for "see")
        convs, msgs, err = await _sync_fetch_conversations(ch["page_id"], ch["page_token"], limit=20)
        if err:
            detail = f"Fetched {convs} conversations (msg probe {msgs}); note: {err[:100]}"
        else:
            detail = f"Synced {convs} conversations, sample messages {msgs}"
    from sqlalchemy import text as _text

    try:
        await db.execute(_text("UPDATE facebook_channels SET last_sync_status=:s, last_sync_at=datetime('now') WHERE page_id=:pid"), {"s": status, "pid": page_id})
        await db.commit()
    except Exception:
        await db.rollback()
    try:
        from app.db.conversation_store import add_sync_log

        await add_sync_log(page_id, status, detail, result.get("error") if not result.get("ok") else None)
    except Exception:
        pass
    return {"status": status, "health": result, "detail": detail}


@router.post("/channels/by-slug/{slug}/sync")
async def channel_sync_by_slug(slug: str, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    from app.services.facebook_channels import get_channel_by_slug

    ch = await get_channel_by_slug(db, slug)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    result = await _health_check(ch["page_id"], ch["page_token"])
    status = "success" if result.get("ok") else "error"
    detail = ""
    if result.get("ok"):
        convs, msgs, err = await _sync_fetch_conversations(ch["page_id"], ch["page_token"], limit=20)
        if err:
            detail = f"Fetched {convs} conversations (msg probe {msgs}); note: {err[:100]}"
        else:
            detail = f"Synced {convs} conversations, sample messages {msgs}"
    from sqlalchemy import text as _text

    try:
        await db.execute(_text("UPDATE facebook_channels SET last_sync_status=:s, last_sync_at=datetime('now') WHERE slug=:slug"), {"s": status, "slug": slug})
        await db.commit()
    except Exception:
        await db.rollback()
    try:
        from app.db.conversation_store import add_sync_log

        await add_sync_log(ch["page_id"], status, detail, result.get("error") if not result.get("ok") else None)
    except Exception:
        pass
    return {"status": status, "health": result, "detail": detail}


@router.post("/channels/{channel_id}/sync")
async def channel_sync(channel_id: str, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    ch = await get_channel(db, channel_id)
    if not ch:
        ch = await get_channel_by_page_id(db, channel_id)
        if not ch:
            from app.services.facebook_channels import get_channel_by_slug

            ch = await get_channel_by_slug(db, channel_id)
    if not ch and channel_id == "legacy-1":
        ch = await get_facebook_config(db)
        if ch:
            ch = dict(id="legacy-1", **ch)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    result = await _health_check(ch["page_id"], ch["page_token"])
    status = "success" if result.get("ok") else "error"
    detail = ""
    if result.get("ok"):
        convs, msgs, err = await _sync_fetch_conversations(ch["page_id"], ch["page_token"], limit=20)
        detail = f"Synced {convs} conversations, sample {msgs}" if not err else f"Fetched {convs} convs; {err[:100]}"
    from sqlalchemy import text as _text

    try:
        # Try channels table; fallback to legacy id=1
        await db.execute(_text("UPDATE facebook_channels SET last_sync_status=:s, last_sync_at=datetime('now') WHERE id=:id"), {"s": status, "id": channel_id})
        await db.commit()
    except Exception:
        try:
            await db.rollback()
            await db.execute(_text("UPDATE facebook_config SET last_sync_status=:s, last_sync_at=datetime('now') WHERE id=1"), {"s": status})
            await db.commit()
        except Exception:
            await db.rollback()
    try:
        from app.db.conversation_store import add_sync_log

        await add_sync_log(ch["page_id"], status, detail, result.get("error") if not result.get("ok") else None)
    except Exception:
        pass
    return {"status": status, "health": result, "detail": detail}


@router.post("/channels/by-slug/{slug}/purge")
async def purge_by_slug(slug: str, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    from app.services.facebook_channels import get_channel_by_slug

    ch = await get_channel_by_slug(db, slug)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    from app.db.conversation_store import purge_conversations_by_page

    deleted = await purge_conversations_by_page(ch["page_id"])
    try:
        from app.db.conversation_store import add_sync_log

        await add_sync_log(ch["page_id"], "purged", f"Purged {deleted} conversations", None)
    except Exception:
        pass
    return {"status": "purged", "deleted": deleted}


@router.post("/channels/{channel_id}/purge")
async def purge_by_id(channel_id: str, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    ch = await get_channel(db, channel_id)
    if not ch:
        ch = await get_channel_by_page_id(db, channel_id)
        if not ch:
            from app.services.facebook_channels import get_channel_by_slug

            ch = await get_channel_by_slug(db, channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    from app.db.conversation_store import purge_conversations_by_page

    deleted = await purge_conversations_by_page(ch["page_id"])
    try:
        from app.db.conversation_store import add_sync_log

        await add_sync_log(ch["page_id"], "purged", f"Purged {deleted} conversations", None)
    except Exception:
        pass
    return {"status": "purged", "deleted": deleted}


@router.get("/channels/{channel_id}/conversations")
async def list_channel_conversations(channel_id: str, limit: int = 10, offset: int = 0, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    ch = await get_channel(db, channel_id)
    if not ch:
        ch = await get_channel_by_page_id(db, channel_id)
        if not ch and channel_id == "legacy-1":
            ch = await get_facebook_config(db)
            if ch:
                ch = dict(id="legacy-1", **ch)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    from app.db.conversation_store import list_sessions_with_meta

    metas = await list_sessions_with_meta(ch["page_id"], limit=limit, offset=offset)
    from app.services.rag import get_messages

    out = []
    for m in metas:
        sid = m["session_id"]
        try:
            msgs = await get_messages(sid)
            last_ai = next((mm for mm in reversed(msgs) if mm["role"] == "assistant"), None)
            last_user = next((mm for mm in reversed(msgs) if mm["role"] == "user"), None)
            out.append({"session_id": sid, "username": m.get("username"), "last_user": last_user, "last_ai": last_ai, "message_count": len(msgs), "updated_at": m.get("updated_at")})
        except Exception:
            continue
    return {"conversations": out, "total": len(out)}


@router.get("/channels/by-page/{page_id}/conversations")
async def list_channel_conversations_by_page(page_id: str, limit: int = 10, offset: int = 0, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    ch = await get_channel_by_page_id(db, page_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    from app.db.conversation_store import list_sessions_with_meta

    metas = await list_sessions_with_meta(page_id, limit=limit, offset=offset)
    from app.services.rag import get_messages

    out = []
    for m in metas:
        sid = m["session_id"]
        try:
            msgs = await get_messages(sid)
            last_ai = next((mm for mm in reversed(msgs) if mm["role"] == "assistant"), None)
            last_user = next((mm for mm in reversed(msgs) if mm["role"] == "user"), None)
            out.append({"session_id": sid, "username": m.get("username"), "last_user": last_user, "last_ai": last_ai, "message_count": len(msgs), "updated_at": m.get("updated_at")})
        except Exception:
            continue
    return {"conversations": out, "total": len(out)}


@router.get("/channels/{channel_id}/sync-history")
async def channel_sync_history(channel_id: str, limit: int = 10, offset: int = 0, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    ch = await get_channel(db, channel_id)
    if not ch:
        ch = await get_channel_by_page_id(db, channel_id)
    page_id = ch["page_id"] if ch else channel_id
    from app.db.conversation_store import list_sync_logs

    logs = await list_sync_logs(page_id, limit=limit, offset=offset)
    return {"logs": logs}


@router.get("/channels/by-page/{page_id}/sync-history")
async def channel_sync_history_by_page(page_id: str, limit: int = 10, offset: int = 0, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    from app.db.conversation_store import list_sync_logs

    logs = await list_sync_logs(page_id, limit=limit, offset=offset)
    return {"logs": logs}


@router.get("/health")
async def health(user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    config = await get_facebook_config(db)
    if not config:
        raise HTTPException(status_code=404, detail="No Facebook config found")
    result = await _health_check(config["page_id"], config["page_token"])
    # Persist last_sync_status for UI badge
    if result.get("ok"):
        from sqlalchemy import text as _text

        sql = "UPDATE facebook_config SET last_sync_status='success', last_sync_at=datetime('now') WHERE id=1"
        try:
            await db.execute(_text(sql))
            await db.commit()
        except Exception:
            await db.rollback()
    return result


@router.post("/sync")
async def sync_now(user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    config = await get_facebook_config(db)
    if not config:
        raise HTTPException(status_code=404, detail="No Facebook config found")
    # ponytail: health + timestamp only; add FetchRecentConversations poll if needed
    result = await _health_check(config["page_id"], config["page_token"])
    from sqlalchemy import text as _text

    status = "success" if result.get("ok") else "error"
    try:
        sql = "UPDATE facebook_config SET last_sync_status=:s, last_sync_at=datetime('now') WHERE id=1"
        await db.execute(_text(sql), {"s": status})
        await db.commit()
    except Exception:
        await db.rollback()
    return {"status": status, "health": result}


@router.get("/webhook/info")
async def webhook_info(user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    config = await get_facebook_config(db)
    # Build webhook URL from request not needed — frontend constructs from API base; return verify_token
    return {
        "webhook_url": "/api/facebook/webhook",
        "verify_token": config.get("verify_token", "") if config else "",
        "has_config": bool(config),
    }


# ---------------------------------------------------------------------------
# Webhook endpoints
# ---------------------------------------------------------------------------

@router.get("/webhook")
async def fb_verify(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
    db: AsyncSession = Depends(get_async_session),
):
    # Check against all channels + legacy single config
    channels = await list_channels(db)
    legacy = await get_facebook_config(db) if not channels else None
    tokens = [c.get("verify_token", "") for c in channels]
    if legacy:
        tokens.append(legacy.get("verify_token", ""))
    matched = hub_verify_token in tokens if tokens else False

    logger.info(
        "Facebook webhook verification: mode=%s token=%s challenge=%s",
        hub_mode,
        hub_verify_token[:10] + "..." if len(hub_verify_token) > 10 else hub_verify_token,
        hub_challenge,
    )

    if hub_mode == "subscribe" and matched and hub_challenge:
        logger.info("Facebook webhook verified successfully")
        return Response(content=hub_challenge, media_type="text/plain")

    logger.warning(
        "Facebook webhook verification failed: mode=%s token_match=%s",
        hub_mode,
        matched,
    )
    return Response(status_code=403)


@router.post("/webhook")
async def fb_webhook(request: Request, db: AsyncSession = Depends(get_async_session)):
    body = await request.json()
    logger.info("Facebook webhook received: object=%s", body.get("object"))

    if body.get("object") != "page":
        logger.warning("Facebook webhook: unexpected object type '%s'", body.get("object"))
        return Response(status_code=404)

    channels = await list_channels(db)
    legacy = await get_facebook_config(db) if not channels else None
    by_page = {c["page_id"]: c for c in channels}
    if legacy and legacy["page_id"] not in by_page:
        by_page[legacy["page_id"]] = legacy

    if not by_page:
        logger.warning("Facebook webhook received but no config saved. Configure in Integrations page.")
        return Response(status_code=200)

    messages_found = 0

    for entry in body.get("entry", []):
        entry_page_id = entry.get("id") or ""
        # Route per entry's page id to correct token; fallback to first channel
        target = by_page.get(entry_page_id) or next(iter(by_page.values()))
        page_id = target["page_id"]
        page_token = target["page_token"]
        for event in entry.get("messaging", []):
            sender_id = event.get("sender", {}).get("id")
            message = event.get("message", {})
            text = message.get("text", "")

            if not sender_id or not text:
                continue

            if sender_id == page_id:
                logger.debug("Skipping message from page itself (sender=%s)", sender_id)
                continue

            messages_found += 1
            logger.info("Facebook message from user %s on page %s: '%s'", sender_id, page_id, text[:100])

            asyncio.create_task(_handle_message(page_id, page_token, sender_id, text))

    if messages_found == 0:
        logger.info("Facebook webhook: no user messages found in event (might be a delivery/read event)")

    return Response(status_code=200)


async def _handle_message(page_id: str, page_token: str, sender_id: str, text: str) -> None:
    try:
        logger.info("Processing Facebook message from %s: '%s'", sender_id, text[:100])

        await mark_seen(page_id, page_token, sender_id)
        await typing_on(page_id, page_token, sender_id)

        response = await answer_question(text, session_id=sender_id)
        reply_text = response.answer
        logger.info("RAG response for %s: '%s'", sender_id, reply_text[:100])
        # Best practice: link PSID session to page for per-channel visibility (no Sync needed for AI-sent view)
        try:
            from app.db.conversation_store import link_page_to_session

            await link_page_to_session(sender_id, page_id)
        except Exception:
            logger.exception("Failed to link page to session")

        if len(reply_text) > 2000:
            reply_text = reply_text[:1997] + "..."

        sent = await send_message(page_id, page_token, sender_id, reply_text)
        if sent:
            logger.info("Reply sent to %s successfully", sender_id)
        else:
            logger.error("Failed to send reply to %s", sender_id)
    except Exception:
        logger.exception("Failed to handle Facebook message from %s", sender_id)
        try:
            await send_message(page_id, page_token, sender_id, "Sorry, something went wrong. Please try again.")
        except Exception:
            logger.exception("Failed to send error message to %s", sender_id)
