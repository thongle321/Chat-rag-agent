from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import Depends
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.user import Base, User

# Resolve absolute path for SQLite DB
_DB_DIR = Path(settings.upload_dir).resolve().parent  # data/
_DB_DIR.mkdir(parents=True, exist_ok=True)
_DB_PATH = _DB_DIR / "app.db"

engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_PATH}")
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def create_db_and_tables():
    """Create all tables (idempotent)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Generic DB session dependency for non-user operations."""
    async with async_session_factory() as session:
        yield session


async def get_user_db() -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
    """Dependency that yields a SQLAlchemyUserDatabase for fastapi-users."""
    async with async_session_factory() as session:
        yield SQLAlchemyUserDatabase(session, User)
