import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import settings


def _derive_key(salt: bytes) -> bytes:
    raw = settings.jwt_secret_key.get_secret_value().encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(raw))


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    salt = os.urandom(16)
    key = _derive_key(salt)
    token = Fernet(key).encrypt(plaintext.encode())
    return (base64.urlsafe_b64encode(salt) + b":" + token).decode()


def decrypt(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        raw = ciphertext.encode()
        sep = raw.index(b":")
        salt = base64.urlsafe_b64decode(raw[:sep])
        token = raw[sep + 1:]
        return Fernet(_derive_key(salt)).decrypt(token).decode()
    except InvalidToken:
        return ciphertext