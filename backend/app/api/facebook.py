import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from httpx import AsyncClient
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.models.user import User
from app.services.facebook_config import (
    delete_facebook_config,
    get_facebook_config,
    save_facebook_config,
)
from app.services.rag import answer_question
from app.services.user_manager import current_active_user
import logging


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


router = APIRouter()


# ---------------------------------------------------------------------------
# Config models
# ---------------------------------------------------------------------------

class FacebookConfigRequest(BaseModel):
    page_id: str
    page_name: str
    page_token: str
    verify_token: str


class FacebookConfigResponse(BaseModel):
    page_id: str
    page_name: str
    has_token: bool
    verify_token: str


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
    )


@router.post("/config", response_model=FacebookConfigResponse)
async def save_config(req: FacebookConfigRequest, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    config = await save_facebook_config(db, req.page_id, req.verify_token, page_token=req.page_token, page_name=req.page_name)

    return FacebookConfigResponse(
        page_id=config["page_id"],
        page_name=config.get("page_name", "Facebook Page"),
        has_token=bool(config.get("page_token")),
        verify_token=config["verify_token"],
    )


@router.delete("/config")
async def delete_config(user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    deleted = await delete_facebook_config(db)
    if not deleted:
        raise HTTPException(status_code=404, detail="No Facebook config found")
    return {"status": "deleted"}


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
    config = await get_facebook_config(db)
    stored_token = config.get("verify_token", "") if config else ""

    logger.info(
        "Facebook webhook verification: mode=%s token=%s challenge=%s",
        hub_mode,
        hub_verify_token[:10] + "..." if len(hub_verify_token) > 10 else hub_verify_token,
        hub_challenge,
    )

    if hub_mode == "subscribe" and hub_verify_token == stored_token and hub_challenge:
        logger.info("Facebook webhook verified successfully")
        return Response(content=hub_challenge, media_type="text/plain")

    logger.warning("Facebook webhook verification failed: mode=%s token_match=%s", hub_mode, hub_verify_token == stored_token)
    return Response(status_code=403)


@router.post("/webhook")
async def fb_webhook(request: Request, db: AsyncSession = Depends(get_async_session)):
    config = await get_facebook_config(db)
    if not config:
        logger.warning("Facebook webhook received but no config saved. Configure in Integrations page.")
        return Response(status_code=200)

    body = await request.json()
    logger.info("Facebook webhook received: object=%s", body.get("object"))

    if body.get("object") != "page":
        logger.warning("Facebook webhook: unexpected object type '%s'", body.get("object"))
        return Response(status_code=404)

    page_id = config["page_id"]
    page_token = config["page_token"]
    messages_found = 0

    for entry in body.get("entry", []):
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
            logger.info("Facebook message from user %s: '%s'", sender_id, text[:100])

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
