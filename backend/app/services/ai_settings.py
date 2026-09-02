import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.ai_settings import AISettingsModel

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
    # 1) Prefer unified KV app_settings (single-tenant, no tenant_id) if any rows exist
    try:
        from sqlalchemy import text as _text

        res = await session.execute(_text("SELECT setting_key, value_plain, value_encrypted FROM app_settings"))
        rows = res.fetchall()
        if rows:
            kv: dict[str, str] = {}
            for k, plain, enc in rows:
                if k in _API_KEY_FIELDS and enc is not None:
                    # enc is bytes (LargeBinary) or str
                    enc_s = enc.decode() if isinstance(enc, (bytes, bytearray)) else enc
                    kv[k] = _decrypt(enc_s)
                else:
                    kv[k] = plain or ""
            # ensure defaults for missing keys
            for k in ["ai_provider", "ollama_base_url", "ollama_model", "openai_model", "zalo_webhook_url"]:
                kv.setdefault(k, "")
            for k in list(_API_KEY_FIELDS):
                kv.setdefault(k, "")
            return kv
    except Exception:
        pass
    # 2) Fallback: legacy single-row ai_settings
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
        "zalo_api_key": getattr(row, "zalo_api_key", ""),
        "zalo_verify_token": getattr(row, "zalo_verify_token", ""),
        "zalo_webhook_url": getattr(row, "zalo_webhook_url", ""),
    }
    for field in _API_KEY_FIELDS & raw.keys():
        raw[field] = _decrypt(raw[field])
    return raw


async def save_ai_settings(session: AsyncSession, data: dict) -> dict:
    encrypted = dict(data)
    for field in _API_KEY_FIELDS & encrypted.keys():
        encrypted[field] = _encrypt(encrypted[field])

    # Dual-write: legacy single-row ai_settings (for rollback) + unified KV app_settings (preferred)
    result = await session.execute(select(AISettingsModel).where(AISettingsModel.id == 1))
    row = result.scalar_one_or_none()
    if row:
        for key, value in encrypted.items():
            if hasattr(row, key):
                setattr(row, key, value)
    else:
        session.add(AISettingsModel(id=1, **encrypted))
    # Unified KV: one row per key, no tenant_id
    try:
        from sqlalchemy import text as _text
        import uuid as _uuid

        for k, v in data.items():
            if k in _API_KEY_FIELDS:
                enc = _encrypt(v) if v else ""
                # upsert by setting_key
                exists = await session.execute(_text("SELECT id FROM app_settings WHERE setting_key=:k"), {"k": k})
                rid = exists.fetchone()
                if rid:
                    await session.execute(_text("UPDATE app_settings SET value_encrypted=:v, value_plain=NULL, updated_at=CURRENT_TIMESTAMP WHERE setting_key=:k"), {"v": enc.encode(), "k": k})
                else:
                    await session.execute(_text("INSERT INTO app_settings (id, setting_key, value_encrypted) VALUES (:id,:k,:v)"), {"id": _uuid.uuid4().hex[:36], "k": k, "v": enc.encode()})
            else:
                exists = await session.execute(_text("SELECT id FROM app_settings WHERE setting_key=:k"), {"k": k})
                rid = exists.fetchone()
                if rid:
                    await session.execute(_text("UPDATE app_settings SET value_plain=:v, value_encrypted=NULL, updated_at=CURRENT_TIMESTAMP WHERE setting_key=:k"), {"v": str(v) if v is not None else "", "k": k})
                else:
                    await session.execute(_text("INSERT INTO app_settings (id, setting_key, value_plain) VALUES (:id,:k,:v)"), {"id": _uuid.uuid4().hex[:36], "k": k, "v": str(v) if v is not None else ""})
    except Exception:
        import logging as _lg

        _lg.getLogger(__name__).debug("app_settings KV write skipped", exc_info=True)
    await session.commit()
    new_row = row or (await session.execute(select(AISettingsModel).where(AISettingsModel.id == 1))).scalar_one()
    logger.info("AI settings saved")
    # Return decrypted legacy row (source of truth for response, KV is in sync)
    return {
        "ai_provider": new_row.ai_provider,
        "ollama_base_url": new_row.ollama_base_url,
        "ollama_model": new_row.ollama_model,
        "ollama_api_key": _decrypt(new_row.ollama_api_key),
        "openai_model": new_row.openai_model,
        "openai_api_key": _decrypt(new_row.openai_api_key),
        "zalo_api_key": _decrypt(getattr(new_row, "zalo_api_key", "")),
        "zalo_verify_token": _decrypt(getattr(new_row, "zalo_verify_token", "")),
        "zalo_webhook_url": getattr(new_row, "zalo_webhook_url", ""),
    }