import re
import unicodedata
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import Mapped

from app.models.user import Base


def slugify(text: str) -> str:
    """Generate a URL-friendly slug from text."""
    text = unicodedata.normalize('NFD', text.lower())
    text = re.sub(r'[\u0300-\u036f]', '', text)
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = text.strip('-')
    return text[:60] or 'channel'


class FacebookChannelModel(Base):
    __tablename__ = "facebook_channels"

    id: Mapped[str] = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    page_id: Mapped[str] = Column(String, unique=True, nullable=False)
    page_name: Mapped[str] = Column(String, default="Facebook Page")
    page_token: Mapped[str] = Column(String, default="")
    verify_token: Mapped[str] = Column(String, default="")
    sync_interval: Mapped[int] = Column(Integer, default=15)
    sync_files: Mapped[bool] = Column(Boolean, default=False)
    last_sync_status: Mapped[str | None] = Column(String, nullable=True)
    last_sync_at: Mapped[str | None] = Column(String, nullable=True)
    created_at: Mapped[datetime | None] = Column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = Column(Boolean, default=True)
    slug: Mapped[str] = Column(String, unique=True, nullable=True, index=True)
