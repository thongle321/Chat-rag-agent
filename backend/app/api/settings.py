import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.services.user_manager import current_active_user
from app.models.user import User


class AISettingsResponse(BaseModel):
    ai_provider: str
    ollama_base_url: str
    ollama_model: str
    openai_model: str
    has_openai_key: bool


class AISettingsUpdate(BaseModel):
    ai_provider: str | None = None
    ollama_base_url: str | None = None
    ollama_model: str | None = None
    openai_api_key: str | None = None
    openai_model: str | None = None


class TestConnectionResponse(BaseModel):
    ok: bool
    message: str


router = APIRouter()


@router.get("/ai", response_model=AISettingsResponse)
async def get_ai_settings(user: User = current_active_user):
    return AISettingsResponse(
        ai_provider=settings.ai_provider,
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
        openai_model=settings.openai_model,
        has_openai_key=bool(settings.openai_api_key),
    )


@router.put("/ai", response_model=AISettingsResponse)
async def update_ai_settings(body: AISettingsUpdate, user: User = current_active_user):
    if body.ai_provider is not None:
        if body.ai_provider not in ("ollama", "openai"):
            raise HTTPException(status_code=400, detail="ai_provider must be 'ollama' or 'openai'")
        settings.ai_provider = body.ai_provider

    if body.ollama_base_url is not None:
        settings.ollama_base_url = body.ollama_base_url

    if body.ollama_model is not None:
        settings.ollama_model = body.ollama_model

    if body.openai_api_key is not None:
        settings.openai_api_key = body.openai_api_key

    if body.openai_model is not None:
        settings.openai_model = body.openai_model

    return AISettingsResponse(
        ai_provider=settings.ai_provider,
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
        openai_model=settings.openai_model,
        has_openai_key=bool(settings.openai_api_key),
    )


@router.post("/test", response_model=TestConnectionResponse)
async def test_connection(user: User = current_active_user):
    provider = settings.ai_provider.lower()

    if provider == "ollama":
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{settings.ollama_base_url}/api/tags")
                resp.raise_for_status()
                return TestConnectionResponse(ok=True, message=f"Connected to Ollama at {settings.ollama_base_url}")
        except httpx.ConnectError:
            return TestConnectionResponse(ok=False, message=f"Cannot connect to Ollama at {settings.ollama_base_url}")
        except Exception as e:
            return TestConnectionResponse(ok=False, message=f"Ollama error: {e}")

    if provider == "openai":
        if not settings.openai_api_key:
            return TestConnectionResponse(ok=False, message="OpenAI API key is not set.")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                )
                resp.raise_for_status()
                return TestConnectionResponse(ok=True, message=f"Connected to OpenAI with model '{settings.openai_model}'.")
        except Exception as e:
            return TestConnectionResponse(ok=False, message=f"OpenAI error: {e}")

    return TestConnectionResponse(ok=False, message=f"Unknown provider '{provider}'.")
