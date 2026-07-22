import secrets
from pathlib import Path

from pydantic_settings import BaseSettings

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
        "You are a knowledgeable assistant for a private document knowledge base.\n"
        "RULES:\n"
        "1) Answer ONLY using the provided context. Do not use outside knowledge.\n"
        "2) Synthesize information across all provided context chunks when answering.\n"
        # "3) Cite sources inline: [Source: filename, p.X] where X is the page number.\n"
        "3) If the context fully answers the question, respond directly.\n"
        "4) If the context partially answers, provide what's available and note what's missing.\n"
        "5) If the context does not contain relevant information, say: \"I don't have enough information in the provided documents to answer this.\"\n"
        "6) If the context contains conflicting information, note the conflict.\n\n"
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
