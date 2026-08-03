import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.password import PasswordHelper
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import settings
from app.db.session import get_user_db
from app.models.user import User

password_hash = PasswordHash((Argon2Hasher(),))
password_helper = PasswordHelper(password_hash)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.jwt_secret_key
    verification_token_secret = settings.jwt_secret_key


async def get_user_manager() -> AsyncGenerator[UserManager, None]:
    async for user_db in get_user_db():
        yield UserManager(user_db, password_helper)


jwt_backend = AuthenticationBackend(
    name="jwt",
    transport=BearerTransport(tokenUrl="api/auth/login"),
    get_strategy=lambda: JWTStrategy(
        secret=settings.jwt_secret_key,
        lifetime_seconds=3600,
    ),
)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [jwt_backend])

current_active_user = Depends(fastapi_users.current_user(active=True))
