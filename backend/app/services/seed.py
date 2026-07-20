from sqlalchemy import select
from fastapi_users.password import PasswordHelper

from app.db.session import async_session_factory
from app.models.user import User


async def seed_admin_user():
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.email == "admin@example.com")
        )
        if result.scalar_one_or_none():
            return

        hashed = PasswordHelper().hash("admin123")
        admin = User(
            email="admin@example.com",
            hashed_password=hashed,
            role="admin",
            is_active=True,
            is_superuser=True,
            is_verified=True,
        )
        session.add(admin)
        await session.commit()
