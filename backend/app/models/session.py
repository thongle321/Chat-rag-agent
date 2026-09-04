from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String, func
from sqlalchemy.orm import Mapped

from app.models.user import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = Column(String, primary_key=True)
    # Owner account id (UUID str); NULL = anonymous/legacy. Sidebar lists per-user.
    user_id: Mapped[str | None] = Column(String(36), nullable=True, index=True)
    title: Mapped[str] = Column(String, default="New chat", nullable=False)
    pinned: Mapped[bool] = Column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
