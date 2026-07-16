from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String, func
from sqlalchemy.orm import Mapped

from app.models.user import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = Column(String, primary_key=True)
    title: Mapped[str] = Column(String, default="Cuộc hội thoại mới", nullable=False)
    pinned: Mapped[bool] = Column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
