from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_settings import AISettingsModel
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def get_ai_settings(session: AsyncSession) -> dict | None:
    result = await session.execute(select(AISettingsModel).where(AISettingsModel.id == 1))
    row = result.scalar_one_or_none()
    if not row:
        return None
    return {
        "ai_provider": row.ai_provider,
        "ollama_base_url": row.ollama_base_url,
        "ollama_model": row.ollama_model,
        "ollama_api_key": row.ollama_api_key,
        "openai_model": row.openai_model,
        "openai_api_key": row.openai_api_key,
    }


async def save_ai_settings(session: AsyncSession, data: dict) -> dict:
    result = await session.execute(select(AISettingsModel).where(AISettingsModel.id == 1))
    row = result.scalar_one_or_none()
    if row:
        for key, value in data.items():
            if hasattr(row, key):
                setattr(row, key, value)
    else:
        session.add(AISettingsModel(id=1, **data))
    await session.commit()
    new_row = row or (await session.execute(select(AISettingsModel).where(AISettingsModel.id == 1))).scalar_one()
    logger.info("AI settings saved")
    return {
        "ai_provider": new_row.ai_provider,
        "ollama_base_url": new_row.ollama_base_url,
        "ollama_model": new_row.ollama_model,
        "ollama_api_key": new_row.ollama_api_key,
        "openai_model": new_row.openai_model,
        "openai_api_key": new_row.openai_api_key,
    }
