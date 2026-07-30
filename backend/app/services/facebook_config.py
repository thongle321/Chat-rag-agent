from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.facebook_config import FacebookConfigModel
import logging


logger = logging.getLogger(__name__)


async def get_facebook_config(session: AsyncSession) -> Optional[dict]:
    result = await session.execute(select(FacebookConfigModel).where(FacebookConfigModel.id == 1))
    row = result.scalar_one_or_none()
    if not row:
        return None
    return {
        "page_id": row.page_id,
        "page_name": row.page_name,
        "page_token": row.page_token,
        "verify_token": row.verify_token,
    }


async def save_facebook_config(
    session: AsyncSession,
    page_id: str,
    verify_token: str,
    page_token: str | None = None,
    page_name: str = "Facebook Page",
) -> dict:
    result = await session.execute(select(FacebookConfigModel).where(FacebookConfigModel.id == 1))
    row = result.scalar_one_or_none()
    if row:
        row.page_id = page_id
        row.page_name = page_name
        row.verify_token = verify_token
        if page_token is not None:
            row.page_token = page_token
    else:
        session.add(FacebookConfigModel(
            id=1,
            page_id=page_id,
            page_name=page_name,
            page_token=page_token or "",
            verify_token=verify_token,
        ))
    await session.commit()
    new_row = row or (await session.execute(select(FacebookConfigModel).where(FacebookConfigModel.id == 1))).scalar_one()
    logger.info("Facebook config saved for page %s", page_id)
    return {
        "page_id": new_row.page_id,
        "page_name": new_row.page_name,
        "page_token": new_row.page_token,
        "verify_token": new_row.verify_token,
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
