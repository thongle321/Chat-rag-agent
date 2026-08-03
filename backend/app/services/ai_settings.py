import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.ai_settings import AISettingsModel

logger = logging.getLogger(__name__)

_API_KEY_FIELDS = {"ollama_api_key", "openai_api_key"}


def _get_key() -> bytes:
    raw = settings.jwt_secret_key.get_secret_value().encode()
    return base64.urlsafe_b64encode(hashlib.sha256(raw).digest())


def _encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    return Fernet(_get_key()).encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return Fernet(_get_key()).decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        return ciphertext


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
        raw[field] = _decrypt(raw[field])
    return raw


async def save_ai_settings(session: AsyncSession, data: dict) -> dict:
    encrypted = dict(data)
    for field in _API_KEY_FIELDS & encrypted.keys():
        encrypted[field] = _encrypt(encrypted[field])

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
        "ollama_api_key": _decrypt(new_row.ollama_api_key),
        "openai_model": new_row.openai_model,
        "openai_api_key": _decrypt(new_row.openai_api_key),
    }