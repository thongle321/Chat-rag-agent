from fastapi import APIRouter

from app.models.user import User
from app.services.user_manager import current_active_user, fastapi_users, jwt_backend

router = APIRouter()

# JWT auth: login, logout
router.include_router(
    fastapi_users.get_auth_router(jwt_backend),
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
