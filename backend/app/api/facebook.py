import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from httpx import AsyncClient
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.conversation_store import (
    add_sync_log,
    link_page_to_session,
    list_sessions_with_meta,
    purge_conversations_by_page,
)
from app.db.session import get_async_session
from app.models.user import User
from app.services.facebook_channels import (
    create_channel,
    delete_channel,
    get_channel_by_identifier,
    list_channels,
    update_channel,
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


VALID_INTERVALS = {1, 5, 10, 15, 30, 60, 360, 1440}


async def _health_check(page_id: str, page_token: str) -> dict:
    """ponytail: probe permission-light endpoint first (/{page_id} needs pages_read_engagement)."""
    for url in (f"{FB_GRAPH_API}/me", f"{FB_GRAPH_API}/{page_id}"):
        resp = await _get_client().get(url, params={"fields": "id,name", "access_token": page_token})
        data = resp.json()
        if resp.status_code == 200 and "error" not in data:
            return {
                "ok": True,
                "page_name": data.get("name", ""),
                "page_id": data.get("id", page_id),
            }
        err = data.get("error", {}) if isinstance(data, dict) else {}
        msg = err.get("message", resp.text[:300]) if err else resp.text[:300]
        code = err.get("code")
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
    try:
        resp = await _get_client().get(
            f"{FB_GRAPH_API}/{page_id}/conversations",
            params={
                "fields": "id,updated_time,participants",
                "limit": min(limit, 50),
                "access_token": page_token,
            },
        )
        data = resp.json()
        if resp.status_code != 200 or "error" in data:
            err = data.get("error", {}).get("message", resp.text[:200]) if isinstance(data, dict) else resp.text[:200]
            return 0, 0, err
        convs = data.get("data", []) if isinstance(data.get("data"), list) else []
        msg_count = 0
        for c in convs:
            # Extract real customer PSID from participants (skip page self)
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
            await link_page_to_session(customer_id, page_id, username=customer_name)
            try:
                all_msgs = []
                msg_url = f"{FB_GRAPH_API}/{c.get('id')}/messages"
                msg_params = {
                    "fields": "id,message,from,created_time",
                    "limit": 100,  # Graph API's per-page cap; pagination below gets the rest
                    "access_token": page_token,
                }

                while msg_url:
                    mr = await _get_client().get(msg_url, params=msg_params)
                    mdata = mr.json()
                    if mr.status_code != 200 or "error" in mdata:
                        break
                    page_msgs = mdata.get("data", [])
                    if not isinstance(page_msgs, list):
                        break
                    all_msgs.extend(page_msgs)

                    next_url = mdata.get("paging", {}).get("next")
                    if next_url:
                        msg_url = next_url
                        msg_params = None  # next_url already carries all query params
                    else:
                        msg_url = None

                if all_msgs:
                    msgs = list(reversed(all_msgs))  # oldest -> newest
                    msg_count += len(msgs)
                    from app.db.conversation_store import load_messages

                    existing = await load_messages(customer_id)
                    if not existing:
                        from pydantic_ai.messages import (
                            ModelRequest,
                            ModelResponse,
                            TextPart,
                            UserPromptPart,
                        )

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
                            from app.db.conversation_store import (
                                save_messages as save_conv_messages,
                            )

                            await save_conv_messages(customer_id, conv_msgs)
            except Exception:
                continue
        try:
            from app.db.conversation_store import cleanup_placeholder_sessions

            await cleanup_placeholder_sessions(page_id)
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


router = APIRouter()


# ---------------------------------------------------------------------------
# Channels CRUD — single deep seam /channels/{identifier}
#   identifier ∈ {id (uuid) | slug | page_id} — resolved by get_channel_by_identifier
# ---------------------------------------------------------------------------


@router.get("/channels", response_model=list[FacebookChannelResponse])
async def list_facebook_channels(user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    channels = await list_channels(db)
    try:
        from app.db.conversation_store import count_sessions_by_page

        for c in channels:
            try:
                c["total_conversations"] = await count_sessions_by_page(c["page_id"])
            except Exception:
                c["total_conversations"] = 0
    except Exception:
        pass
    return [_channel_to_response(c) for c in channels]


@router.post("/channels", response_model=FacebookChannelResponse)
async def create_facebook_channel(
    req: FacebookChannelRequest, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)
):
    if req.sync_interval is not None and req.sync_interval not in VALID_INTERVALS:
        raise HTTPException(status_code=400, detail="Invalid sync_interval")
    ch = await create_channel(
        db,
        req.page_id,
        req.page_name,
        req.page_token,
        req.verify_token,
        req.sync_interval or 15,
        False,
    )
    try:
        from app.db.conversation_store import count_sessions_by_page

        ch["total_conversations"] = await count_sessions_by_page(ch["page_id"])
    except Exception:
        pass
    return _channel_to_response(ch)


@router.get("/channels/{identifier}", response_model=FacebookChannelResponse)
async def get_facebook_channel(
    identifier: str, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)
):
    ch = await get_channel_by_identifier(db, identifier)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    try:
        from app.db.conversation_store import count_sessions_by_page

        ch["total_conversations"] = await count_sessions_by_page(ch["page_id"])
    except Exception:
        pass
    return _channel_to_response(ch)


@router.put("/channels/{identifier}", response_model=FacebookChannelResponse)
async def update_facebook_channel(
    identifier: str,
    req: FacebookChannelUpdateRequest,
    user: User = current_active_user,
    db: AsyncSession = Depends(get_async_session),
):
    if req.sync_interval is not None and req.sync_interval not in VALID_INTERVALS:
        raise HTTPException(status_code=400, detail="Invalid sync_interval")
    ch = await get_channel_by_identifier(db, identifier)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    updated = await update_channel(
        db,
        ch["id"],
        req.page_name,
        req.page_token,
        req.verify_token,
        req.sync_interval,
        None,
        req.is_active,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Channel not found")
    try:
        from app.db.conversation_store import count_sessions_by_page

        updated["total_conversations"] = await count_sessions_by_page(updated["page_id"])
    except Exception:
        pass
    return _channel_to_response(updated)


@router.delete("/channels/{identifier}")
async def delete_facebook_channel(
    identifier: str, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)
):
    ch = await get_channel_by_identifier(db, identifier)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    ok = await delete_channel(db, ch["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Channel not found")
    # Delete anything related but NOT conversations: clear sync logs
    try:
        from app.db.conversation_store import delete_sync_logs_by_page

        await delete_sync_logs_by_page(ch["page_id"])
    except Exception:
        pass
    return {"status": "deleted"}


@router.get("/channels/{identifier}/health")
async def channel_health(
    identifier: str, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)
):
    ch = await get_channel_by_identifier(db, identifier)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    result = await _health_check(ch["page_id"], ch["page_token"])
    # Health only checks, no sync side-effects (no DB update, no fetch)
    return result


@router.post("/channels/{identifier}/sync")
async def channel_sync(
    identifier: str, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)
):
    ch = await get_channel_by_identifier(db, identifier)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    result = await _health_check(ch["page_id"], ch["page_token"])
    status = "success" if result.get("ok") else "error"
    detail = ""
    if result.get("ok"):
        convs, msgs, err = await _sync_fetch_conversations(ch["page_id"], ch["page_token"], limit=20)
        detail = f"Synced {convs} conversations, sample {msgs}" if not err else f"Fetched {convs} convs; {err[:100]}"
    try:
        from app.db.conversation_store import update_last_sync_status

        await update_last_sync_status(ch["id"], status)
    except Exception:
        pass
    try:
        await add_sync_log(
            ch["page_id"],
            status,
            detail,
            result.get("error") if not result.get("ok") else None,
        )
    except Exception:
        pass
    return {"status": status, "health": result, "detail": detail}


@router.post("/channels/{identifier}/purge")
async def channel_purge(
    identifier: str, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)
):
    ch = await get_channel_by_identifier(db, identifier)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    deleted = await purge_conversations_by_page(ch["page_id"])
    try:
        await add_sync_log(ch["page_id"], "purged", f"Purged {deleted} conversations", None)
    except Exception:
        pass
    return {"status": "purged", "deleted": deleted}


@router.get("/channels/{identifier}/conversations")
async def list_channel_conversations(
    identifier: str,
    limit: int = 10,
    offset: int = 0,
    user: User = current_active_user,
    db: AsyncSession = Depends(get_async_session),
):
    ch = await get_channel_by_identifier(db, identifier)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    metas = await list_sessions_with_meta(ch["page_id"], limit=limit, offset=offset)
    from app.services.rag import get_messages

    out = []
    for m in metas:
        sid = m["session_id"]
        try:
            msgs = await get_messages(sid)
            last_ai = next((mm for mm in reversed(msgs) if mm["role"] == "assistant"), None)
            last_user = next((mm for mm in reversed(msgs) if mm["role"] == "user"), None)
            out.append(
                {
                    "session_id": sid,
                    "username": m.get("username"),
                    "last_user": last_user,
                    "last_ai": last_ai,
                    "message_count": len(msgs),
                    "updated_at": m.get("updated_at"),
                }
            )
        except Exception:
            continue
    return {"conversations": out, "total": len(out)}


@router.get("/channels/{identifier}/sync-history")
async def channel_sync_history(
    identifier: str,
    limit: int = 10,
    offset: int = 0,
    user: User = current_active_user,
    db: AsyncSession = Depends(get_async_session),
):
    ch = await get_channel_by_identifier(db, identifier)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")

    logs = await _list_sync_logs_for(ch["page_id"], limit=limit, offset=offset)

    return {"logs": logs}


async def _list_sync_logs_for(page_id: str, limit: int = 10, offset: int = 0) -> list[dict]:
    from app.db.conversation_store import list_sync_logs

    return await list_sync_logs(page_id, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# Webhook endpoints
# ---------------------------------------------------------------------------


@router.get("/webhook/info")
async def webhook_info(user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    channels = await list_channels(db)
    first = channels[0] if channels else None
    return {
        "webhook_url": "/api/facebook/webhook",
        "verify_token": first.get("verify_token", "") if first else "",
        "has_config": bool(first),
    }


@router.get("/webhook")
async def fb_verify(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
    db: AsyncSession = Depends(get_async_session),
):
    channels = await list_channels(db)
    tokens = [c.get("verify_token", "") for c in channels]
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
    by_page = {c["page_id"]: c for c in channels}

    if not by_page:
        logger.warning("Facebook webhook received but no config saved. Configure in Integrations page.")
        return Response(status_code=200)

    messages_found = 0

    for entry in body.get("entry", []):
        entry_page_id = entry.get("id") or ""
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
        try:
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
