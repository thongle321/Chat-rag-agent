import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient
from zalo_bot import Bot
from zalo_bot.error import InvalidToken, ZaloError

from app.db.conversation_store import add_sync_log, list_sync_logs
from app.db.session import get_async_session
from app.models.user import User
from app.services.rag import answer_question
from app.services.user_manager import current_active_user
from app.services.zalo_channels import (
    create_channel,
    delete_channel,
    get_channel_by_identifier,
    list_channels,
    update_channel,
    update_last_sync_status,
)

logger = logging.getLogger(__name__)

ZALO_BASE_URL = "https://bot-api.zaloplatforms.com"
ZALO_API = ZALO_BASE_URL

_client: AsyncClient | None = None


def _get_client() -> AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = AsyncClient(timeout=30)
    return _client


def _zalo_url(token: str, method: str) -> str:
    return f"{ZALO_API}/bot{token}/{method}"


async def _with_bot(bot_token: str):
    bot = Bot(token=bot_token, base_url=ZALO_BASE_URL)
    await bot._request[0].initialize()
    await bot._request[1].initialize()
    return bot


async def _shutdown_bot(bot: Bot):
    try:
        await bot._request[0].shutdown()
        await bot._request[1].shutdown()
    except Exception:
        pass


async def _zalo_get_me(bot_token: str) -> dict:
    bot = await _with_bot(bot_token)
    try:
        user = await bot.get_me()
        return {"ok": True, "bot_id": str(user.id), "account_name": getattr(user, "account_name", ""), "result": {"id": user.id, "account_name": getattr(user, "account_name", "")}}
    except (InvalidToken, ZaloError) as e:
        return {"ok": False, "error": str(e)[:300]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}
    finally:
        await _shutdown_bot(bot)


async def _zalo_send_message(bot_token: str, chat_id: str, text: str) -> bool:
    if len(text) > 2000:
        text = text[:1997] + "..."
    bot = await _with_bot(bot_token)
    try:
        await bot.send_message(chat_id=chat_id, text=text)
        return True
    except ZaloError as e:
        if getattr(e, "error_code", None) == 429 or "429" in str(e):
            logger.warning("Zalo quota exceeded for chat %s: %s", chat_id, e)
        else:
            logger.error("Zalo send failed: %s", e)
        return False
    except Exception as e:
        logger.error("Zalo send exception: %s", e)
        return False
    finally:
        await _shutdown_bot(bot)


async def _zalo_send_chat_action(bot_token: str, chat_id: str) -> None:
    bot = await _with_bot(bot_token)
    try:
        await bot.send_chat_action(chat_id=chat_id, action="typing")
    except Exception:
        pass
    finally:
        await _shutdown_bot(bot)


async def _zalo_set_webhook(bot_token: str, url: str, secret_token: str) -> dict:
    # use httpx to inspect verification{ok,outcome,hint} per bot.zapps.me/docs/apis/setWebhook
    try:
        resp = await _get_client().post(_zalo_url(bot_token, "setWebhook"), json={"url": url, "secret_token": secret_token})
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        ver = (data.get("result") or {}).get("verification") or {}
        if data.get("ok") and ver.get("ok"):
            return {"ok": True, "result": data.get("result")}
        # Zalo docs: URL still saved even on verification failure — surface hint
        hint = ver.get("hint") or ver.get("outcome") or data.get("description") or resp.text[:300]
        return {"ok": False, "description": hint, "result": data.get("result"), "verification": ver}
    except Exception as e:
        return {"ok": False, "description": str(e)[:300]}


class ZaloChannelRequest(BaseModel):
    bot_token: str
    verify_token: str
    webhook_url: str | None = None
    bot_username: str | None = None


class ZaloChannelUpdateRequest(BaseModel):
    bot_username: str | None = None
    bot_token: str | None = None
    verify_token: str | None = None
    webhook_url: str | None = None
    is_active: bool | None = None


class ZaloChannelResponse(BaseModel):
    id: str
    bot_id: str
    bot_username: str
    has_token: bool
    verify_token: str
    webhook_url: str
    last_sync_status: str | None = None
    last_sync_at: str | None = None
    created_at: str | None = None
    is_active: bool = True
    total_conversations: int = 0
    slug: str | None = None


def _to_response(ch: dict) -> ZaloChannelResponse:
    return ZaloChannelResponse(
        id=ch["id"],
        bot_id=ch["bot_id"],
        bot_username=ch.get("bot_username", ""),
        has_token=bool(ch.get("bot_token")),
        verify_token=ch.get("verify_token", ""),
        webhook_url=ch.get("webhook_url", ""),
        last_sync_status=ch.get("last_sync_status"),
        last_sync_at=ch.get("last_sync_at"),
        created_at=ch.get("created_at"),
        is_active=bool(ch.get("is_active", True)),
        total_conversations=ch.get("total_conversations", 0),
        slug=ch.get("slug"),
    )


router = APIRouter()


@router.get("/channels", response_model=list[ZaloChannelResponse])
async def list_zalo_channels(user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    channels = await list_channels(db)
    for c in channels:
        # plan A backfill: ensure bot_username is account_name
        if not c.get("bot_username") and c.get("bot_token"):
            try:
                me = await _zalo_get_me(c["bot_token"])
                if me.get("ok"):
                    an = me.get("account_name") or me.get("result", {}).get("account_name", "")
                    if an:
                        await update_channel(db, c["id"], an, None, None, None, None)
                        c["bot_username"] = an
            except Exception:
                pass
        try:
            from app.db.conversation_store import count_sessions_by_page

            c["total_conversations"] = await count_sessions_by_page(c["bot_id"], channel_type="zalo")
        except Exception:
            c["total_conversations"] = 0
    return [_to_response(c) for c in channels]


@router.post("/channels", response_model=ZaloChannelResponse)
async def create_zalo_channel(req: ZaloChannelRequest, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    if len(req.verify_token) < 8 or len(req.verify_token) > 256:
        raise HTTPException(status_code=400, detail="verify_token must be 8..256 chars")
    me = await _zalo_get_me(req.bot_token)
    if not me.get("ok"):
        raise HTTPException(status_code=400, detail=me.get("error", "Invalid bot_token"))
    bot_id = me.get("bot_id") or me.get("result", {}).get("id", "")
    # plan A: always account_name from getMe (e.g. bot.VDKyGxQvc), ignore manual Bot Username — per bot.zapps.me/docs/apis/getMe
    bot_username = me.get("account_name") or me.get("result", {}).get("account_name", "") or bot_id
    # ponytail: verify webhook before DB commit to avoid orphan 409 on retry (see bot.zapps.me/docs/apis/setWebhook verification)
    if req.webhook_url:
        res = await _zalo_set_webhook(req.bot_token, req.webhook_url, req.verify_token)
        if not res.get("ok"):
            logger.warning("Zalo setWebhook verification failed %s: %s", bot_id, res)
            raise HTTPException(status_code=400, detail=f"Webhook verification failed: {res.get('description') or res.get('hint') or 'verification failed'} — use public HTTPS like https://<ngrok>.ngrok-free.app/api/zalo/webhook")
        logger.info("Zalo setWebhook %s ok", bot_id)
    ch = await create_channel(db, bot_id, bot_username, req.bot_token, req.verify_token, req.webhook_url or "")
    return _to_response(ch)


@router.get("/channels/{identifier}", response_model=ZaloChannelResponse)
async def get_zalo_channel(identifier: str, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    ch = await get_channel_by_identifier(db, identifier)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    return _to_response(ch)


@router.put("/channels/{identifier}", response_model=ZaloChannelResponse)
async def update_zalo_channel(identifier: str, req: ZaloChannelUpdateRequest, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    ch = await get_channel_by_identifier(db, identifier)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    # plan A: ignore req.bot_username, always sync account_name from getMe if token is available
    effective_username: str | None = None
    if req.bot_token:
        me2 = await _zalo_get_me(req.bot_token)
        if me2.get("ok"):
            effective_username = me2.get("account_name") or me2.get("result", {}).get("account_name", "")
    elif ch.get("bot_token"):
        # keep existing account_name, but refresh from stored token to stay accurate
        me2 = await _zalo_get_me(ch["bot_token"])
        if me2.get("ok"):
            effective_username = me2.get("account_name") or me2.get("result", {}).get("account_name", "")
    updated = await update_channel(db, ch["id"], effective_username, req.bot_token, req.verify_token, req.webhook_url, req.is_active)
    if not updated:
        raise HTTPException(status_code=404, detail="Channel not found")
    if req.bot_token or req.webhook_url or req.verify_token:
        token = req.bot_token or ch["bot_token"]
        url = req.webhook_url if req.webhook_url is not None else updated.get("webhook_url") or ch.get("webhook_url")
        secret = req.verify_token or updated.get("verify_token") or ch.get("verify_token")
        if url and token and secret:
            try:
                await _zalo_set_webhook(token, url, secret)
            except Exception:
                pass
    return _to_response(updated)


@router.delete("/channels/{identifier}")
async def delete_zalo_channel(identifier: str, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    ch = await get_channel_by_identifier(db, identifier)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    ok = await delete_channel(db, ch["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Channel not found")
    try:
        from app.db.conversation_store import delete_sync_logs_by_page

        await delete_sync_logs_by_page(ch["bot_id"], channel_type="zalo")
    except Exception:
        pass
    return {"status": "deleted"}


@router.get("/channels/{identifier}/health")
async def zalo_health(identifier: str, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    ch = await get_channel_by_identifier(db, identifier)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    return await _zalo_get_me(ch["bot_token"])


@router.get("/channels/{identifier}/conversations")
async def list_zalo_conversations(identifier: str, limit: int | None = None, offset: int = 0, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    ch = await get_channel_by_identifier(db, identifier)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    from app.db.conversation_store import list_sessions_with_meta

    metas = await list_sessions_with_meta(ch["bot_id"], limit=limit, offset=offset, channel_type="zalo")
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


@router.get("/channels/{identifier}/sync-history")
async def zalo_sync_history(identifier: str, limit: int = 10, offset: int = 0, user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    ch = await get_channel_by_identifier(db, identifier)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    from app.db.conversation_store import list_sync_logs

    logs = await list_sync_logs(ch["bot_id"], limit=limit, offset=offset, channel_type="zalo")
    return {"logs": logs}


@router.get("/webhook/info")
async def webhook_info(user: User = current_active_user, db: AsyncSession = Depends(get_async_session)):
    channels = await list_channels(db)
    first = channels[0] if channels else None
    return {"webhook_url": "/api/zalo/webhook", "verify_token": first.get("verify_token", "") if first else "", "has_config": bool(first)}


@router.post("/webhook")
async def zalo_webhook(request: Request, db: AsyncSession = Depends(get_async_session)):
    secret = request.headers.get("x-bot-api-secret-token", "")
    body = await request.json()
    logger.info("Zalo webhook received: %s", str(body)[:500])

    result = body.get("result") if isinstance(body, dict) else None
    if not result:
        # also accept flat {event_name, message}
        result = body if isinstance(body.get("event_name"), str) else None
    if not result or not isinstance(result, dict):
        return Response(status_code=200)

    event_name = result.get("event_name", "")
    message = result.get("message", {}) if isinstance(result.get("message"), dict) else {}

    channels = await list_channels(db)
    if not channels:
        return Response(status_code=200)
    tokens = [c.get("verify_token", "") for c in channels]
    if secret not in tokens:
        logger.warning("Zalo webhook secret mismatch: got %s", secret[:8] if secret else "<empty>")
        return Response(status_code=403)

    if event_name == "message.unsupported.received":
        return Response(status_code=200)

    # Extract text — handle text / image caption / sticker fallback
    text = message.get("text") or message.get("caption") or ""
    if not text:
        return Response(status_code=200)

    chat = message.get("chat", {}) if isinstance(message.get("chat"), dict) else {}
    from_user = message.get("from", {}) if isinstance(message.get("from"), dict) else {}
    chat_id = str(chat.get("id") or from_user.get("id") or "")
    if not chat_id:
        return Response(status_code=200)
    display_name = from_user.get("display_name") or chat.get("chat_type") or ""

    target = None
    for c in channels:
        if c.get("verify_token") == secret:
            target = c
            break
    if not target:
        logger.warning("Zalo webhook secret has no matching channel")
        return Response(status_code=403)

    bot_token = target["bot_token"]
    asyncio.create_task(_handle_message(target["bot_id"], bot_token, chat_id, text, display_name))
    return Response(status_code=200)


async def _handle_message(bot_id: str, bot_token: str, chat_id: str, text: str, display_name: str) -> None:
    try:
        logger.info("Processing Zalo message from %s: '%s'", chat_id, text[:100])
        await _zalo_send_chat_action(bot_token, chat_id)
        from app.services.rag import answer_question
        from app.db.conversation_store import link_page_to_session

        response = await answer_question(text, session_id=chat_id)
        reply_text = response.answer
        if len(reply_text) > 2000:
            reply_text = reply_text[:1997] + "..."
        try:
            await link_page_to_session(chat_id, bot_id, username=display_name or None, channel_type="zalo")
        except Exception:
            logger.exception("Failed to link zalo page to session")
        sent = await _zalo_send_message(bot_token, chat_id, reply_text)
        if sent:
            logger.info("Zalo reply sent to %s", chat_id)
        else:
            logger.error("Failed to send Zalo reply to %s", chat_id)
    except Exception:
        logger.exception("Failed to handle Zalo message from %s", chat_id)
        try:
            await _zalo_send_message(bot_token, chat_id, "Sorry, something went wrong. Please try again.")
        except Exception:
            logger.exception("Failed to send Zalo error message to %s", chat_id)
