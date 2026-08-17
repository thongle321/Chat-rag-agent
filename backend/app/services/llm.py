import logging

from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider

from app.core.config import settings

logger = logging.getLogger(__name__)

_instance = None
_instance_name = None
_key: str | None = None


def get_llm():
    """Return a (model, display_name) pair, cached per configured provider/model."""
    global _instance, _instance_name, _key
    provider = settings.ai_provider.lower()
    model_name = settings.ollama_model if provider == "ollama" else settings.openai_model
    key = f"{provider}:{model_name}"
    if _key == key:
        return _instance, _instance_name
    if provider == "ollama":
        _instance = OllamaModel(
            settings.ollama_model,
            provider=OllamaProvider(
                base_url=settings.ollama_base_url or "http://localhost:11434",
                api_key=(
                    settings.ollama_api_key.get_secret_value()
                    if hasattr(settings.ollama_api_key, "get_secret_value")
                    else settings.ollama_api_key
                )
                or None,
            ),
        )
        _instance_name = f"ollama/{settings.ollama_model}"
    elif provider == "openai":
        openai_key = (
            settings.openai_api_key.get_secret_value()
            if hasattr(settings.openai_api_key, "get_secret_value")
            else settings.openai_api_key
        )
        _instance = OpenAIChatModel(
            settings.openai_model,
            provider=OpenAIProvider(api_key=openai_key or None),
        )
        _instance_name = f"openai/{settings.openai_model}"
    else:
        raise ValueError("No LLM configured")
    _key = key
    return _instance, _instance_name
