import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import settings


_SALT_PREFIX = b"crypto-salt-v1:"


def _derive_key(salt: bytes) -> bytes:
    raw = settings.jwt_secret_key.get_secret_value().encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(raw))


def _old_derive_key() -> bytes:
    raw = settings.jwt_secret_key.get_secret_value()
    import hashlib

    key = hashlib.sha256(raw.encode()).digest()
    return base64.urlsafe_b64encode(key)


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    salt = os.urandom(16)
    key = _derive_key(salt)
    token = Fernet(key).encrypt(plaintext.encode())
    return (_SALT_PREFIX + base64.urlsafe_b64encode(salt) + b":" + token).decode()


def decrypt(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        raw = ciphertext.encode()
        if raw.startswith(_SALT_PREFIX):
            rest = raw[len(_SALT_PREFIX):]
            sep = rest.index(b":")
            salt = base64.urlsafe_b64decode(rest[:sep])
            token = rest[sep + 1:]
            return Fernet(_derive_key(salt)).decrypt(token).decode()
        return Fernet(_old_derive_key()).decrypt(raw).decode()
    except InvalidToken:
        return ciphertext
