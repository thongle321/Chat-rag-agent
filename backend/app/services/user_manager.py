import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)

from app.core.config import settings
from app.db.session import get_user_db
from app.models.user import User


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = "reset-password-secret"
    verification_token_secret = "verification-secret"


async def get_user_manager() -> AsyncGenerator[UserManager, None]:
    async for user_db in get_user_db():
        yield UserManager(user_db)


jwt_backend = AuthenticationBackend(
    name="jwt",
    transport=BearerTransport(tokenUrl="api/auth/login"),
    get_strategy=lambda: JWTStrategy(
        # ponytail: fallback until Task 7 adds jwt_secret_key to settings
        secret=getattr(settings, "jwt_secret_key", "dev-secret-change-me"),
        lifetime_seconds=3600,
    ),
)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [jwt_backend])

current_active_user = Depends(fastapi_users.current_user(active=True))
