import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.facebook_config import FacebookConfigModel
from app.services.encryption import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)


async def _ensure_sync_columns(session: AsyncSession) -> None:
    # ponytail: lightweight migration for existing DBs missing sync columns
    try:
        from sqlalchemy import text
        for _col, ddl in [
            ("sync_interval", "ALTER TABLE facebook_config ADD COLUMN sync_interval INTEGER DEFAULT 15"),
            ("sync_files", "ALTER TABLE facebook_config ADD COLUMN sync_files BOOLEAN DEFAULT 0"),
            ("last_sync_status", "ALTER TABLE facebook_config ADD COLUMN last_sync_status TEXT"),
            ("last_sync_at", "ALTER TABLE facebook_config ADD COLUMN last_sync_at TEXT"),
            ("created_at", "ALTER TABLE facebook_config ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ]:
            try:
                await session.execute(text(ddl))
            except Exception:
                await session.rollback()
        await session.commit()
    except Exception:
        pass


async def get_facebook_config(session: AsyncSession) -> dict | None:
    await _ensure_sync_columns(session)
    result = await session.execute(select(FacebookConfigModel).where(FacebookConfigModel.id == 1))
    row = result.scalar_one_or_none()
    if not row:
        return None
    cre = getattr(row, "created_at", None)
    # sqlite returns str for TIMESTAMP default; normalize to iso if str
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
        "page_id": row.page_id,
        "page_name": row.page_name,
        "page_token": decrypt_token(row.page_token),
        "verify_token": row.verify_token,
        "sync_interval": getattr(row, "sync_interval", 15) or 15,
        "sync_files": bool(getattr(row, "sync_files", False)),
        "last_sync_status": getattr(row, "last_sync_status", None),
        "last_sync_at": getattr(row, "last_sync_at", None),
        "created_at": cre_iso,
    }


async def save_facebook_config(
    session: AsyncSession,
    page_id: str,
    verify_token: str,
    page_token: str | None = None,
    page_name: str = "Facebook Page",
    sync_interval: int | None = None,
    sync_files: bool | None = None,
) -> dict:
    await _ensure_sync_columns(session)
    enc_token = encrypt_token(page_token) if page_token is not None else None
    result = await session.execute(select(FacebookConfigModel).where(FacebookConfigModel.id == 1))
    row = result.scalar_one_or_none()
    if row:
        row.page_id = page_id
        row.page_name = page_name
        row.verify_token = verify_token
        if enc_token is not None:
            row.page_token = enc_token
        if sync_interval is not None:
            row.sync_interval = sync_interval
        if sync_files is not None:
            row.sync_files = sync_files
    else:
        session.add(FacebookConfigModel(
            id=1,
            page_id=page_id,
            page_name=page_name,
            page_token=enc_token or "",
            verify_token=verify_token,
            sync_interval=sync_interval or 15,
            sync_files=bool(sync_files),
        ))
    await session.commit()
    result = await session.execute(select(FacebookConfigModel).where(FacebookConfigModel.id == 1))
    new_row = row or result.scalar_one()
    logger.info("Facebook config saved for page %s", page_id)
    cre2 = getattr(new_row, "created_at", None)
    if isinstance(cre2, str):
        cre2_iso = cre2
    elif cre2:
        try:
            cre2_iso = cre2.isoformat()
        except Exception:
            cre2_iso = str(cre2)
    else:
        cre2_iso = None
    return {
        "page_id": new_row.page_id,
        "page_name": new_row.page_name,
        "page_token": decrypt_token(new_row.page_token),
        "verify_token": new_row.verify_token,
        "sync_interval": getattr(new_row, "sync_interval", 15) or 15,
        "sync_files": bool(getattr(new_row, "sync_files", False)),
        "last_sync_status": getattr(new_row, "last_sync_status", None),
        "last_sync_at": getattr(new_row, "last_sync_at", None),
        "created_at": cre2_iso,
    }


async def delete_facebook_config(session: AsyncSession) -> bool:
    result = await session.execute(select(FacebookConfigModel).where(FacebookConfigModel.id == 1))
    row = result.scalar_one_or_none()
    if not row:
        return False
    await session.delete(row)
    await session.commit()
    logger.info("Facebook config deleted")
    return True
