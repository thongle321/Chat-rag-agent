import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet | None:
    key = settings.encryption_key.get_secret_value() if settings.encryption_key else None
    if not key:
        return None
    # Accept 32-byte raw or base64 urlsafe 44-char Fernet key; derive if plain
    try:
        # Try as valid Fernet key (44 urlsafe base64)
        Fernet(key.encode())
        return Fernet(key.encode())
    except Exception:
        pass
    # Derive deterministically from arbitrary string (ponytail: not KDF-rotated, replace if needed)
    digest = hashlib.sha256(key.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(digest)
    return Fernet(fernet_key)


def encrypt_token(plain: str) -> str:
    f = _get_fernet()
    if not f or not plain:
        return plain
    try:
        return f.encrypt(plain.encode()).decode()
    except Exception:
        logger.exception("encrypt failed")
        return plain


def decrypt_token(cipher: str) -> str:
    f = _get_fernet()
    if not f or not cipher:
        return cipher
    try:
        return f.decrypt(cipher.encode()).decode()
    except InvalidToken:
        # Not encrypted (legacy plain) — return as-is
        return cipher
    except Exception:
        logger.exception("decrypt failed")
        return cipher
