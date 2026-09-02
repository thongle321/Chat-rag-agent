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

# --- Strict role isolation (industry practice: backend is source of truth, frontend guard is UX only)
# Single session: one JWT in localStorage; role is a JWT claim via DB lookup — no concurrent admin+user.
# Best practice (OWASP/RBAC): authenticate first, then authorize per-resource; never trust frontend role alone.
# See: RBAC guide (roles → permissions), SuperTokens route protection, Vue/Next RBAC examples via web_search.
from fastapi import HTTPException


async def require_admin(user: User = Depends(fastapi_users.current_user(active=True))) -> User:
    if user.role != "admin" and not user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin only — please log in as admin")
    return user


async def require_user(user: User = Depends(fastapi_users.current_user(active=True))) -> User:
    # Strict separation: admin must log out before using user chat (prevents privilege mixing)
    if user.role == "admin" or user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin cannot access user chat — log out and use a user account")
    return user


current_admin_user = Depends(require_admin)
current_user_user = Depends(require_user)
