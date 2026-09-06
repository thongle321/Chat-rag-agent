import asyncio
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.db.vector_store import get_vector_store
from app.models.schemas import StatsResponse
from app.models.session import ChatSession
from app.models.user import User
from app.services.rag import get_messages
from app.services.user_manager import current_admin_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
async def get_stats(db: AsyncSession = Depends(get_async_session), user: User = current_admin_user):
    """Aggregate stats for the dashboard."""
    # Documents + chunks
    docs = await asyncio.to_thread(get_vector_store().list_documents)
    total_documents = len(docs)
    total_chunks = await asyncio.to_thread(get_vector_store().count)

    # Sessions — account sessions only (guest/temporary rows have user_id NULL)
    result = await db.execute(select(func.count(ChatSession.id)).where(ChatSession.user_id.is_not(None)))
    total_sessions = result.scalar() or 0

    # Total queries — sum message counts across recent sessions (bounded scan)
    total_queries = 0
    if total_sessions:
        session_result = await db.execute(
            select(ChatSession.id)
            .where(ChatSession.user_id.is_not(None))
            .order_by(ChatSession.updated_at.desc())
            .limit(500)
        )
        session_ids = [r[0] for r in session_result.all()]
        for sid in session_ids:
            try:
                msgs = await get_messages(sid)
                total_queries += sum(1 for m in msgs if m["role"] == "user")
            except Exception:
                logger.exception("Skipping corrupt conversation for stats: %s", sid)

    # Conversations + messages split by channel (web = NULL, facebook = fb channels)
    from app.models.unified import Channel, Conversation, Message

    fb_channel_ids = select(Channel.id).where(Channel.channel_type == "facebook")
    web_convs_q = select(func.count(Conversation.id)).where(Conversation.channel_id.is_(None))
    fb_convs_q = select(func.count(Conversation.id)).where(Conversation.channel_id.in_(fb_channel_ids))
    web_convs = (await db.execute(web_convs_q)).scalar() or 0
    fb_convs = (await db.execute(fb_convs_q)).scalar() or 0
    # Message counts use the same definition as the admin messages list
    # (get_messages): only UserPromptPart/TextPart entries. save_messages also
    # persists agent plumbing (tool calls/returns) as rows — those aren't messages.
    from pydantic_ai.messages import (
        ModelMessagesTypeAdapter,
        ModelRequest,
        ModelResponse,
        TextPart,
        UserPromptPart,
    )

    fb_ids = set((await db.execute(fb_channel_ids)).scalars().all())
    msg_rows = (
        await db.execute(
            select(Message.raw_data, Conversation.channel_id).join(
                Conversation, Message.conversation_id == Conversation.id
            )
        )
    ).all()
    total_msgs = 0
    for raw, ch_id in msg_rows:
        if not raw:
            continue
        if ch_id is not None and ch_id not in fb_ids:  # zalo etc. — ignored by design
            continue
        try:
            (m,) = ModelMessagesTypeAdapter.validate_json(f"[{raw}]")
        except Exception:
            continue
        if isinstance(m, ModelRequest):
            n = sum(1 for p in m.parts if isinstance(p, UserPromptPart))
        elif isinstance(m, ModelResponse):
            n = sum(1 for p in m.parts if isinstance(p, TextPart))
        else:
            n = 0
        total_msgs += n

    # Active channels — is_active toggle on the user-managed tables (fb + zalo)
    from app.models.facebook_channel import FacebookChannelModel
    from app.models.zalo_channel import ZaloChannelModel

    fb_active_q = select(func.count()).select_from(FacebookChannelModel).where(FacebookChannelModel.is_active.is_(True))
    zalo_active_q = select(func.count()).select_from(ZaloChannelModel).where(ZaloChannelModel.is_active.is_(True))
    fb_active = (await db.execute(fb_active_q)).scalar() or 0
    zalo_active = (await db.execute(zalo_active_q)).scalar() or 0

    return StatsResponse(
        total_documents=total_documents,
        total_chunks=total_chunks,
        total_sessions=total_sessions,
        total_queries=total_queries,
        web_conversations=web_convs,
        facebook_conversations=fb_convs,
        total_conversations=web_convs + fb_convs,
        total_messages=total_msgs,
        active_channels=fb_active + zalo_active,
    )
