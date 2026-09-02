"""Fresh DB — app_settings KV only (no tenant_id, no legacy ai_settings fallback)."""

import base64
import hashlib
import logging
import uuid

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)

_API_KEY_FIELDS = {"ollama_api_key", "openai_api_key", "zalo_api_key", "zalo_verify_token"}


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
    """Read from unified KV app_settings (single-tenant). Fresh DB — no legacy fallback."""
    res = await session.execute(text("SELECT setting_key, value_plain, value_encrypted FROM app_settings"))
    rows = res.fetchall()
    if not rows:
        return None
    kv: dict[str, str] = {}
    for k, plain, enc in rows:
        if k in _API_KEY_FIELDS and enc is not None:
            enc_s = enc.decode() if isinstance(enc, (bytes, bytearray)) else enc
            kv[k] = _decrypt(enc_s)
        else:
            kv[k] = plain or ""
    for k in ["ai_provider", "ollama_base_url", "ollama_model", "openai_model", "zalo_webhook_url"]:
        kv.setdefault(k, "")
    for k in list(_API_KEY_FIELDS):
        kv.setdefault(k, "")
    return kv


async def save_ai_settings(session: AsyncSession, data: dict) -> dict:
    """Upsert into app_settings KV (one row per key). Fresh DB — no legacy table."""
    for k, v in data.items():
        if k in _API_KEY_FIELDS:
            enc = _encrypt(v) if v else ""
            exists = await session.execute(text("SELECT id FROM app_settings WHERE setting_key=:k"), {"k": k})
            rid = exists.fetchone()
            if rid:
                await session.execute(
                    text("UPDATE app_settings SET value_encrypted=:v, value_plain=NULL, updated_at=CURRENT_TIMESTAMP WHERE setting_key=:k"),
                    {"v": enc.encode(), "k": k},
                )
            else:
                await session.execute(
                    text("INSERT INTO app_settings (id, setting_key, value_encrypted) VALUES (:id,:k,:v)"),
                    {"id": uuid.uuid4().hex[:36], "k": k, "v": enc.encode()},
                )
        else:
            exists = await session.execute(text("SELECT id FROM app_settings WHERE setting_key=:k"), {"k": k})
            rid = exists.fetchone()
            if rid:
                await session.execute(
                    text("UPDATE app_settings SET value_plain=:v, value_encrypted=NULL, updated_at=CURRENT_TIMESTAMP WHERE setting_key=:k"),
                    {"v": str(v) if v is not None else "", "k": k},
                )
            else:
                await session.execute(
                    text("INSERT INTO app_settings (id, setting_key, value_plain) VALUES (:id,:k,:v)"),
                    {"id": uuid.uuid4().hex[:36], "k": k, "v": str(v) if v is not None else ""},
                )
    await session.commit()
    logger.info("AI settings saved")
    # Return decrypted view (read back)
    res = await session.execute(text("SELECT setting_key, value_plain, value_encrypted FROM app_settings"))
    rows = res.fetchall()
    kv: dict[str, str] = {}
    for k, plain, enc in rows:
        if k in _API_KEY_FIELDS and enc is not None:
            enc_s = enc.decode() if isinstance(enc, (bytes, bytearray)) else enc
            kv[k] = _decrypt(enc_s)
        else:
            kv[k] = plain or ""
    for k in ["ai_provider", "ollama_base_url", "ollama_model", "openai_model", "zalo_webhook_url"]:
        kv.setdefault(k, "")
    for k in list(_API_KEY_FIELDS):
        kv.setdefault(k, "")
    return kv
