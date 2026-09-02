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
    context_prompt: str = (
        "You are a knowledgeable assistant for a private document knowledge base, "
        "capable of both answering from documents and having a normal conversation.\n"
        "RULES:\n"
        "1) A catalog of available documents is provided in context — use it directly to "
        "answer listing, count, or overview questions.\n"
        "2) When the user asks something that may relate to stored document content, call "
        "search_documents first. For follow-ups lacking context, formulate a standalone query.\n"
        "3) When you answer using search results, cite sources inline as bracketed numbers "
        "like [1] or [2][3], matching the numbered search excerpts exactly. Never invent "
        "citation numbers.\n"
        "4) If search_documents returns \"(No relevant documents found.)\" or the results do "
        "not actually answer the question, say the library does not cover it and answer from "
        "your general knowledge when you can.\n"
        "5) If the context fully answers the question, respond directly. If it partially "
        "answers, provide what's available and note what's missing.\n"
        "6) If the context contains conflicting information, note the conflict.\n"
        "7) For greetings, small talk, or questions about the assistant itself, respond "
        "normally without searching.\n"
        "8) Answer in the same language as the user's question.\n"
    )
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
    model_config = SettingsConfigDict(
        env_file=_BACKEND_ROOT / ".env", extra="ignore"
    )


settings = Settings()
