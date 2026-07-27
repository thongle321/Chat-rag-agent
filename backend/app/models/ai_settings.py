from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import Mapped

from app.models.user import Base


class AISettingsModel(Base):
    __tablename__ = "ai_settings"

    id: Mapped[int] = Column(Integer, primary_key=True, default=1)
    ai_provider: Mapped[str] = Column(String, default="ollama")
    ollama_base_url: Mapped[str] = Column(String, default="http://localhost:11434")
    ollama_model: Mapped[str] = Column(String, default="")
    ollama_api_key: Mapped[str] = Column(String, default="")
    openai_model: Mapped[str] = Column(String, default="")
    openai_api_key: Mapped[str] = Column(String, default="")
