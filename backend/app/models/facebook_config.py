from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import Mapped

from app.models.user import Base


class FacebookConfigModel(Base):
    __tablename__ = "facebook_config"

    id: Mapped[int] = Column(Integer, primary_key=True, default=1)
    page_id: Mapped[str] = Column(String, nullable=False)
    page_name: Mapped[str] = Column(String, default="Facebook Page")
    page_token: Mapped[str] = Column(String, default="")
    verify_token: Mapped[str] = Column(String, default="")
    # Facebook-only sync settings (ported from tanviet12/chat-quality-agent Channels.vue metadata)
    sync_interval: Mapped[int] = Column(Integer, default=15)
    sync_files: Mapped[bool] = Column(Boolean, default=False)
    last_sync_status: Mapped[str | None] = Column(String, nullable=True)
    last_sync_at: Mapped[str | None] = Column(String, nullable=True)
    created_at: Mapped[datetime | None] = Column(DateTime, default=datetime.utcnow)
