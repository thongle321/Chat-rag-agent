import logging
import re
import unicodedata
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.facebook_channel import FacebookChannelModel
from app.models.facebook_config import FacebookConfigModel
from app.services.encryption import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)


def slugify(text: str) -> str:
    """Generate a URL-friendly slug from text."""
    text = unicodedata.normalize('NFD', text.lower())
    text = re.sub(r'[\u0300-\u036f]', '', text)
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = text.strip('-')
    return text[:60] or 'channel'


async def _ensure_table(session: AsyncSession) -> None:
    # ponytail: create if not exists via Base metadata on startup already, but ensure columns for existing DBs
    try:
        from app.db.session import engine
        from sqlalchemy import text

        async with engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: FacebookChannelModel.__table__.create(sync_conn, checkfirst=True))
            try:
                await conn.execute(text("ALTER TABLE facebook_channels ADD COLUMN slug VARCHAR"))
            except Exception:
                pass
    except Exception:
        pass
    # Backfill missing slugs
    try:
        rows = (await session.execute(select(FacebookChannelModel).where(FacebookChannelModel.slug.is_(None)))).scalars().all()
        for row in rows:
            base = slugify(row.page_name or row.page_id)
            slug = base
            cnt = 1
            while True:
                chk = await session.execute(select(FacebookChannelModel).where(FacebookChannelModel.slug == slug))
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
    # Migrate from old facebook_config id=1 if channels empty
    try:
        res = await session.execute(select(FacebookChannelModel).limit(1))
        if res.scalars().first() is None:
            old = await session.execute(select(FacebookConfigModel).where(FacebookConfigModel.id == 1))
            row = old.scalar_one_or_none()
            if row:
                ch = FacebookChannelModel(
                    id=str(uuid.uuid4()),
                    page_id=row.page_id,
                    page_name=getattr(row, "page_name", "Facebook Page"),
                    page_token=row.page_token,
                    verify_token=getattr(row, "verify_token", ""),
                    sync_interval=getattr(row, "sync_interval", 15) or 15,
                    sync_files=bool(getattr(row, "sync_files", False)),
                    last_sync_status=getattr(row, "last_sync_status", None),
                    last_sync_at=getattr(row, "last_sync_at", None),
                    created_at=getattr(row, "created_at", None),
                    is_active=True,
                )
                session.add(ch)
                await session.commit()
                logger.info("Migrated facebook_config id=1 to channels id=%s", ch.id)
    except Exception:
        logger.exception("Channel migration check failed")
        try:
            await session.rollback()
        except Exception:
            pass


def _to_dict(row: FacebookChannelModel) -> dict:
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
        "page_id": row.page_id,
        "page_name": row.page_name,
        "page_token": decrypt_token(row.page_token),
        "verify_token": row.verify_token,
        "sync_interval": getattr(row, "sync_interval", 15) or 15,
        "sync_files": bool(getattr(row, "sync_files", False)),
        "last_sync_status": getattr(row, "last_sync_status", None),
        "last_sync_at": getattr(row, "last_sync_at", None),
        "created_at": cre_iso,
        "is_active": bool(getattr(row, "is_active", True)),
        "slug": getattr(row, "slug", None),
    }


async def list_channels(session: AsyncSession) -> list[dict]:
    await _ensure_table(session)
    res = await session.execute(select(FacebookChannelModel).order_by(FacebookChannelModel.created_at))
    return [_to_dict(r) for r in res.scalars().all()]


async def get_channel(session: AsyncSession, channel_id: str) -> dict | None:
    await _ensure_table(session)
    res = await session.execute(select(FacebookChannelModel).where(FacebookChannelModel.id == channel_id))
    row = res.scalar_one_or_none()
    return _to_dict(row) if row else None


async def get_channel_by_page_id(session: AsyncSession, page_id: str) -> dict | None:
    await _ensure_table(session)
    res = await session.execute(select(FacebookChannelModel).where(FacebookChannelModel.page_id == page_id))
    row = res.scalar_one_or_none()
    return _to_dict(row) if row else None


async def get_channel_by_slug(session: AsyncSession, slug: str) -> dict | None:
    await _ensure_table(session)
    res = await session.execute(select(FacebookChannelModel).where(FacebookChannelModel.slug == slug))
    row = res.scalar_one_or_none()
    return _to_dict(row) if row else None


async def create_channel(
    session: AsyncSession,
    page_id: str,
    page_name: str,
    page_token: str,
    verify_token: str,
    sync_interval: int = 15,
    sync_files: bool = False,
) -> dict:
    await _ensure_table(session)
    # Unique page_id check
    existing = await session.execute(select(FacebookChannelModel).where(FacebookChannelModel.page_id == page_id))
    if existing.scalar_one_or_none():
        from fastapi import HTTPException

        raise HTTPException(status_code=409, detail=f"Page {page_id} already connected")

    # Generate unique slug
    base_slug = slugify(page_name)
    slug = base_slug
    counter = 1
    while True:
        existing_slug = await session.execute(select(FacebookChannelModel).where(FacebookChannelModel.slug == slug))
        if not existing_slug.scalar_one_or_none():
            break
        counter += 1
        slug = f"{base_slug}-{counter}"

    ch = FacebookChannelModel(
        id=str(uuid.uuid4()),
        page_id=page_id,
        page_name=page_name,
        page_token=encrypt_token(page_token),
        verify_token=verify_token,
        sync_interval=sync_interval,
        sync_files=sync_files,
        is_active=True,
        slug=slug,
    )
    session.add(ch)
    await session.commit()
    await session.refresh(ch)
    logger.info("Facebook channel created %s page %s", ch.id, page_id)
    return _to_dict(ch)


async def update_channel(
    session: AsyncSession,
    channel_id: str,
    page_name: str | None = None,
    page_token: str | None = None,
    verify_token: str | None = None,
    sync_interval: int | None = None,
    sync_files: bool | None = None,
    is_active: bool | None = None,
) -> dict | None:
    await _ensure_table(session)
    res = await session.execute(select(FacebookChannelModel).where(FacebookChannelModel.id == channel_id))
    row = res.scalar_one_or_none()
    if not row:
        return None
    if page_name is not None:
        row.page_name = page_name
    if page_token is not None:
        row.page_token = encrypt_token(page_token)
    if verify_token is not None:
        row.verify_token = verify_token
    if sync_interval is not None:
        row.sync_interval = sync_interval
    if sync_files is not None:
        row.sync_files = sync_files
    if is_active is not None:
        row.is_active = is_active
    await session.commit()
    await session.refresh(row)
    return _to_dict(row)


async def delete_channel(session: AsyncSession, channel_id: str) -> bool:
    await _ensure_table(session)
    res = await session.execute(select(FacebookChannelModel).where(FacebookChannelModel.id == channel_id))
    row = res.scalar_one_or_none()
    if not row:
        return False
    await session.delete(row)
    await session.commit()
    logger.info("Facebook channel deleted %s", channel_id)
    return True
