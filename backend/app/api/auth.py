import uuid

from fastapi import APIRouter
from fastapi_users import schemas

from app.models.user import User
from app.services.user_manager import current_active_user, fastapi_users, jwt_backend


class UserRead(schemas.BaseUser[uuid.UUID]):
    role: str


class UserCreate(schemas.BaseUserCreate):
    pass

router = APIRouter()

# JWT auth: login, logout
router.include_router(
    fastapi_users.get_auth_router(jwt_backend),
    tags=["auth"],
)
# Registration for regular users (same JWT, creates active user)
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    tags=["auth"],
)


@router.get("/me", tags=["auth"])
async def get_me(user: User = current_active_user):
    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
    }
