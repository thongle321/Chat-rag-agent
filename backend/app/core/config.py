from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    app_name: str = "VeilAi Rag"
    version: str = "0.1.0"
    environment: str = "development"
    ai_provider: str = "ollama"
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-5.5"
    ollama_api_key: SecretStr = SecretStr("")
    ollama_base_url: str = "https://ollama.com/v1"
    ollama_model: str = "gemma4:31b-cloud"
    logfire_token: SecretStr | None = None
    hf_token: SecretStr | None = None
    embedding_model: str = "intfloat/multilingual-e5-small"
    jwt_secret_key: SecretStr
    encryption_key: SecretStr | None = None
    zalo_api_key: SecretStr = SecretStr("")
    zalo_verify_token: SecretStr = SecretStr("")
    zalo_webhook_url: str = ""
    upload_dir: str = str(_BACKEND_ROOT / "data" / "uploads")
    vector_store_dir: str = str(_BACKEND_ROOT / ".chromadb")
    retrieval_k: int = 8
    retrieval_rrf_k: int = 60
    retrieval_distance_threshold: float | None = None
    retrieval_bm25_overretrieve: int = 2
    model_config = SettingsConfigDict(env_file=_BACKEND_ROOT / ".env", extra="ignore")


settings = Settings()
