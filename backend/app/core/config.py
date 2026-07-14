from pathlib import Path

from pydantic_settings import BaseSettings


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
    embedding_model: str = "microsoft/harrier-oss-v1-270m"

    # System prompt for the RAG agent
    context_prompt: str = (
        "You are a strict, citation-focused assistant for a private knowledge base.\n"
        "RULES:\n"
        "1) Use ONLY the provided context to answer.\n "
        "2) If the answer is not clearly contained in the context, say: \"I don't know based on the provided documents.\"\n "
        "3) Do NOT use outside knowledge, guessing, or web information.\n"
        "4) If applicable, cite sources as (source:page) using the metadata.\n\n"

    )

    # Storage
    upload_dir: str = "data/uploads"
    vector_store_dir: str = ".chromadb"

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

    def persist(self) -> None:
        env_path = Path(".env")
        lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []

        updates = {
            "AI_PROVIDER": self.ai_provider,
            "OLLAMA_BASE_URL": self.ollama_base_url,
            "OLLAMA_MODEL": self.ollama_model,
            "OPENAI_API_KEY": self.openai_api_key,
            "OPENAI_MODEL": self.openai_model,
        }

        keys_written = set()
        new_lines = []
        for line in lines:
            key = line.split("=", 1)[0].strip() if "=" in line else None
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                keys_written.add(key)
            else:
                new_lines.append(line)

        for key, val in updates.items():
            if key not in keys_written:
                new_lines.append(f"{key}={val}")

        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


settings = Settings()
