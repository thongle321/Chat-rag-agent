import secrets
from pathlib import Path

from pydantic_settings import BaseSettings

# backend/ directory — computed once at import time
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # App
    app_name: str = "Chat RAG Agent"
    version: str = "0.1.0"
    environment: str = "development"

    # AI Provider
    ai_provider: str = "ollama"  # "ollama" or "openai"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-5.4"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma4:31b-cloud"

    # Embeddings (local, no API key needed)
    embedding_model: str = "intfloat/multilingual-e5-small"

    # System prompt for the RAG agent
    context_prompt: str = (
        "You are a strict, citation-focused assistant for a private knowledge base.\n"
        "RULES:\n"
        "1) Use ONLY the provided context to answer.\n"
        "2) If the answer is not clearly contained in the context, say: \"I don't know based on the provided documents.\"\n"
        "3) Do NOT use outside knowledge, guessing, or web information.\n\n"
    )

    jwt_secret_key: str = ""

    # Storage
    upload_dir: str = str(_BACKEND_ROOT / "data" / "uploads")
    vector_store_dir: str = str(_BACKEND_ROOT / ".chromadb")

    # CORS
    allowed_cors_origins: str = "*"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    def get_cors_origins(self) -> list[str]:
        if self.allowed_cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.allowed_cors_origins.split(",")]


settings = Settings()
