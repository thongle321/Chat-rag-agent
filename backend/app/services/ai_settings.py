from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_settings import AISettingsModel
from app.utils.crypto import decrypt, encrypt
from app.utils.logger import get_logger

logger = get_logger(__name__)

_API_KEY_FIELDS = {"ollama_api_key", "openai_api_key"}


async def get_ai_settings(session: AsyncSession) -> dict | None:
    result = await session.execute(select(AISettingsModel).where(AISettingsModel.id == 1))
    row = result.scalar_one_or_none()
    if not row:
        return None
    raw = {
        "ai_provider": row.ai_provider,
        "ollama_base_url": row.ollama_base_url,
        "ollama_model": row.ollama_model,
        "ollama_api_key": row.ollama_api_key,
        "openai_model": row.openai_model,
        "openai_api_key": row.openai_api_key,
    }
    for field in _API_KEY_FIELDS & raw.keys():
        raw[field] = decrypt(raw[field])
    return raw


async def save_ai_settings(session: AsyncSession, data: dict) -> dict:
    encrypted = dict(data)
    for field in _API_KEY_FIELDS & encrypted.keys():
        encrypted[field] = encrypt(encrypted[field])

    result = await session.execute(select(AISettingsModel).where(AISettingsModel.id == 1))
    row = result.scalar_one_or_none()
    if row:
        for key, value in encrypted.items():
            if hasattr(row, key):
                setattr(row, key, value)
    else:
        session.add(AISettingsModel(id=1, **encrypted))
    await session.commit()
    new_row = row or (await session.execute(select(AISettingsModel).where(AISettingsModel.id == 1))).scalar_one()
    logger.info("AI settings saved")
    return {
        "ai_provider": new_row.ai_provider,
        "ollama_base_url": new_row.ollama_base_url,
        "ollama_model": new_row.ollama_model,
        "ollama_api_key": decrypt(new_row.ollama_api_key),
        "openai_model": new_row.openai_model,
        "openai_api_key": decrypt(new_row.openai_api_key),
    }
