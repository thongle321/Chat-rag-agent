import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine
from app.models.zalo_channel import ZaloChannelModel, slugify
from app.services.encryption import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)

VN_TZ = timezone(timedelta(hours=7))


async def _ensure_table(session: AsyncSession) -> None:
    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: ZaloChannelModel.__table__.create(sync_conn, checkfirst=True))
            try:
                await conn.execute(text("ALTER TABLE zalo_channels ADD COLUMN slug VARCHAR"))
            except Exception:
                pass
    except Exception:
        pass
    try:
        rows = (await session.execute(select(ZaloChannelModel).where(ZaloChannelModel.slug.is_(None)))).scalars().all()
        for row in rows:
            base = slugify(row.bot_username or row.bot_id)
            slug = base
            cnt = 1
            while True:
                chk = await session.execute(select(ZaloChannelModel).where(ZaloChannelModel.slug == slug))
                if not chk.scalar_one_or_none():
                    break
                cnt += 1
                slug = f"{base}-{cnt}"
            row.slug = slug
        if rows:
            await session.commit()
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass


def _to_dict(row: ZaloChannelModel) -> dict:
    cre = getattr(row, "created_at", None)
    if isinstance(cre, str):
        cre_iso = cre
    elif cre:
        try:
            cre_iso = cre.isoformat()
        except Exception:
            cre_iso = str(cre)
    else:
        cre_iso = None
    return {
        "id": row.id,
        "bot_id": row.bot_id,
        "bot_username": row.bot_username,
        "bot_token": decrypt_token(row.bot_token),
        "verify_token": row.verify_token,
        "webhook_url": row.webhook_url,
        "last_sync_status": getattr(row, "last_sync_status", None),
        "last_sync_at": getattr(row, "last_sync_at", None),
        "created_at": cre_iso,
        "is_active": bool(getattr(row, "is_active", True)),
        "slug": getattr(row, "slug", None),
    }


async def list_channels(session: AsyncSession) -> list[dict]:
    await _ensure_table(session)
    res = await session.execute(select(ZaloChannelModel).order_by(ZaloChannelModel.created_at))
    return [_to_dict(r) for r in res.scalars().all()]


async def get_channel(session: AsyncSession, channel_id: str) -> dict | None:
    await _ensure_table(session)
    res = await session.execute(select(ZaloChannelModel).where(ZaloChannelModel.id == channel_id))
    row = res.scalar_one_or_none()
    return _to_dict(row) if row else None


async def get_channel_by_bot_id(session: AsyncSession, bot_id: str) -> dict | None:
    await _ensure_table(session)
    res = await session.execute(select(ZaloChannelModel).where(ZaloChannelModel.bot_id == bot_id))
    row = res.scalar_one_or_none()
    return _to_dict(row) if row else None


async def get_channel_by_slug(session: AsyncSession, slug: str) -> dict | None:
    await _ensure_table(session)
    res = await session.execute(select(ZaloChannelModel).where(ZaloChannelModel.slug == slug))
    row = res.scalar_one_or_none()
    return _to_dict(row) if row else None


async def get_channel_by_identifier(session: AsyncSession, identifier: str) -> dict | None:
    await _ensure_table(session)
    for col in (ZaloChannelModel.id, ZaloChannelModel.slug, ZaloChannelModel.bot_id):
        res = await session.execute(select(ZaloChannelModel).where(col == identifier))
        row = res.scalar_one_or_none()
        if row:
            return _to_dict(row)
    return None


async def create_channel(
    session: AsyncSession,
    bot_id: str,
    bot_username: str,
    bot_token: str,
    verify_token: str,
    webhook_url: str = "",
) -> dict:
    await _ensure_table(session)
    existing = await session.execute(select(ZaloChannelModel).where(ZaloChannelModel.bot_id == bot_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Bot {bot_id} already connected")
    base_slug = slugify(bot_username or bot_id)
    slug = base_slug
    counter = 1
    while True:
        es = await session.execute(select(ZaloChannelModel).where(ZaloChannelModel.slug == slug))
        if not es.scalar_one_or_none():
            break
        counter += 1
        slug = f"{base_slug}-{counter}"
    ch = ZaloChannelModel(
        id=str(uuid.uuid4()),
        bot_id=bot_id,
        bot_username=bot_username,
        bot_token=encrypt_token(bot_token),
        verify_token=verify_token,
        webhook_url=webhook_url,
        is_active=True,
        slug=slug,
    )
    session.add(ch)
    await session.commit()
    await session.refresh(ch)
    logger.info("Zalo channel created %s bot %s", ch.id, bot_id)
    return _to_dict(ch)


async def update_channel(
    session: AsyncSession,
    channel_id: str,
    bot_username: str | None = None,
    bot_token: str | None = None,
    verify_token: str | None = None,
    webhook_url: str | None = None,
    is_active: bool | None = None,
) -> dict | None:
    await _ensure_table(session)
    res = await session.execute(select(ZaloChannelModel).where(ZaloChannelModel.id == channel_id))
    row = res.scalar_one_or_none()
    if not row:
        return None
    if bot_username is not None:
        row.bot_username = bot_username
    if bot_token is not None:
        row.bot_token = encrypt_token(bot_token)
    if verify_token is not None:
        row.verify_token = verify_token
    if webhook_url is not None:
        row.webhook_url = webhook_url
    if is_active is not None:
        row.is_active = is_active
    await session.commit()
    await session.refresh(row)
    return _to_dict(row)


async def update_last_sync_status(session: AsyncSession, channel_id: str, status: str) -> dict | None:
    await _ensure_table(session)
    res = await session.execute(select(ZaloChannelModel).where(ZaloChannelModel.id == channel_id))
    row = res.scalar_one_or_none()
    if not row:
        return None
    row.last_sync_status = status
    row.last_sync_at = datetime.now(VN_TZ).isoformat()
    await session.commit()
    await session.refresh(row)
    logger.info("Zalo channel %s sync status updated: %s", channel_id, status)
    return _to_dict(row)


async def delete_channel(session: AsyncSession, channel_id: str) -> bool:
    await _ensure_table(session)
    res = await session.execute(select(ZaloChannelModel).where(ZaloChannelModel.id == channel_id))
    row = res.scalar_one_or_none()
    if not row:
        return False
    await session.delete(row)
    await session.commit()
    logger.info("Zalo channel deleted %s", channel_id)
    return True
