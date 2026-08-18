from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped

from app.models.user import Base

PENDING = "pending"
PROCESSING = "processing"
COMPLETED = "completed"
FAILED = "failed"


class DocumentStatus(Base):
    __tablename__ = "document_status"

    filename: Mapped[str] = Column(String, primary_key=True)
    status: Mapped[str] = Column(String, default=PENDING, nullable=False)
    chunk_count: Mapped[int] = Column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = Column(String, nullable=True)
    updated_at: Mapped[datetime] = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )