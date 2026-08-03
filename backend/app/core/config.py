from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    app_name: str = "Chat RAG Agent"
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
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    context_prompt: str = (
        "You are a knowledgeable assistant for a private document knowledge base.\n"
        "RULES:\n"
        "1) Answer ONLY using the provided context. Do not use outside knowledge.\n"
        "2) Synthesize information across all provided context chunks when answering.\n"
        "3) If the context fully answers the question, respond directly.\n"
        "4) If the context partially answers, provide what's available and note what's missing.\n"
        "5) If the context does not contain relevant information, say: "
        '"I don\'t have enough information in the provided documents to answer this."\n'
        "6) If the context contains conflicting information, note the conflict.\n\n"
    )
    chat_prompt: str = (
        "You are a friendly assistant for a document knowledge base. "
        "Respond warmly and concisely to greetings, small talk, thanks, or questions about yourself. "
        "If a list of available documents is provided below, use it to answer questions about which "
        "documents or topics are available; otherwise say you have no documents. Answer in the user's language."
    )
    jwt_secret_key: SecretStr
    upload_dir: str = str(_BACKEND_ROOT / "data" / "uploads")
    vector_store_dir: str = str(_BACKEND_ROOT / ".chromadb")
    model_config = SettingsConfigDict(
        env_file=_BACKEND_ROOT / ".env", extra="ignore"
    )


settings = Settings()
