from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import Mapped

from app.models.user import Base


class FacebookConfigModel(Base):
    __tablename__ = "facebook_config"

    id: Mapped[int] = Column(Integer, primary_key=True, default=1)
    page_id: Mapped[str] = Column(String, nullable=False)
    page_name: Mapped[str] = Column(String, default="Facebook Page")
    page_token: Mapped[str] = Column(String, default="")
    verify_token: Mapped[str] = Column(String, default="")
