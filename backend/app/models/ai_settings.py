from sqlalchemy.orm import Mapped, mapped_column

from app.models.user import Base


class AISettingsModel(Base):
    __tablename__ = "ai_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    ai_provider: Mapped[str] = mapped_column(default="ollama")
    ollama_base_url: Mapped[str] = mapped_column(default="http://localhost:11434")
    ollama_model: Mapped[str] = mapped_column(default="")
    ollama_api_key: Mapped[str] = mapped_column(default="")
    openai_model: Mapped[str] = mapped_column(default="")
    openai_api_key: Mapped[str] = mapped_column(default="")
