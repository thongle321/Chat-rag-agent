from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_async_session
from app.services.user_manager import current_active_user
from app.models.user import User
from app.services.ai_settings import save_ai_settings


class AISettingsResponse(BaseModel):
    ai_provider: str
    ollama_base_url: str
    ollama_model: str
    ollama_api_key: str = ""
    openai_model: str
    openai_api_key: str = ""


class AISettingsUpdate(BaseModel):
    ai_provider: Literal["ollama", "openai"] | None = None
    ollama_base_url: str | None = None
    ollama_model: str | None = None
    ollama_api_key: str | None = None
    openai_api_key: str | None = None
    openai_model: str | None = None


class TestConnectionRequest(BaseModel):
    provider: str | None = None
    ollama_base_url: str | None = None
    ollama_api_key: str | None = None
    openai_api_key: str | None = None


class TestConnectionResponse(BaseModel):
    ok: bool
    message: str


class ListModelsRequest(BaseModel):
    provider: str | None = None
    ollama_base_url: str | None = None
    ollama_api_key: str | None = None
    openai_api_key: str | None = None


class ListModelsResponse(BaseModel):
    models: list[str]


router = APIRouter()


@router.get("/ai", response_model=AISettingsResponse)
async def get_ai_settings(user: User = current_active_user):
    return AISettingsResponse(
        ai_provider=settings.ai_provider,
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
        ollama_api_key=_get_secret_value(settings.ollama_api_key),
        openai_model=settings.openai_model,
        openai_api_key=_get_secret_value(settings.openai_api_key),
    )


def _get_secret_value(v):
    return v.get_secret_value() if hasattr(v, 'get_secret_value') else v or ""


@router.put("/ai", response_model=AISettingsResponse)
async def update_ai_settings(body: AISettingsUpdate, user: User = current_active_user, session: AsyncSession = Depends(get_async_session)):
    if body.ai_provider is not None:
        settings.ai_provider = body.ai_provider

    if body.ollama_base_url is not None:
        url = body.ollama_base_url.rstrip("/")
        if url.endswith("/api"):
            url = url[:-4]
        settings.ollama_base_url = url

    if body.ollama_model is not None:
        settings.ollama_model = body.ollama_model

    if body.ollama_api_key is not None:
        settings.ollama_api_key = SecretStr(body.ollama_api_key)

    if body.openai_api_key is not None:
        settings.openai_api_key = SecretStr(body.openai_api_key)

    if body.openai_model is not None:
        settings.openai_model = body.openai_model

    await save_ai_settings(session, {
        "ai_provider": settings.ai_provider,
        "ollama_base_url": settings.ollama_base_url,
        "ollama_model": settings.ollama_model,
        "ollama_api_key": _get_secret_value(settings.ollama_api_key),
        "openai_model": settings.openai_model,
        "openai_api_key": _get_secret_value(settings.openai_api_key),
    })

    return AISettingsResponse(
        ai_provider=settings.ai_provider,
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
        ollama_api_key=_get_secret_value(settings.ollama_api_key),
        openai_model=settings.openai_model,
        openai_api_key=_get_secret_value(settings.openai_api_key),
    )


@router.post("/test", response_model=TestConnectionResponse)
async def test_connection(body: TestConnectionRequest, user: User = current_active_user):
    provider = (body.provider or settings.ai_provider).lower()
    ollama_base_url = body.ollama_base_url or settings.ollama_base_url or "http://localhost:11434"
    ollama_key = body.ollama_api_key or _get_secret_value(settings.ollama_api_key)
    openai_key = body.openai_api_key or _get_secret_value(settings.openai_api_key)

    if provider == "ollama":
        headers = {}
        if ollama_key:
            headers["Authorization"] = f"Bearer {ollama_key}"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{ollama_base_url}/api/chat",
                    headers=headers,
                    json={"model": "placeholder", "messages": [{"role": "user", "content": "hi"}], "stream": False},
                )
                if resp.status_code == 401:
                    return TestConnectionResponse(ok=False, message="Invalid API key")
                return TestConnectionResponse(ok=True, message=f"Connected to Ollama at {ollama_base_url}")
        except httpx.ConnectError:
            return TestConnectionResponse(ok=False, message=f"Cannot connect to Ollama at {ollama_base_url}")
        except Exception as e:
            return TestConnectionResponse(ok=False, message=f"Ollama error: {e}")

    if provider == "openai":
        if not openai_key:
            return TestConnectionResponse(ok=False, message="OpenAI API key is not set.")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {openai_key}"},
                )
                resp.raise_for_status()
                return TestConnectionResponse(ok=True, message=f"Connected to OpenAI.")
        except Exception as e:
            return TestConnectionResponse(ok=False, message=f"OpenAI error: {e}")

    return TestConnectionResponse(ok=False, message=f"Unknown provider '{provider}'.")


@router.get("/models", response_model=ListModelsResponse)
async def list_models(body: ListModelsRequest | None = None, user: User = current_active_user):
    provider = (body.provider if body else None) or settings.ai_provider
    ollama_base_url = (body.ollama_base_url if body else None) or settings.ollama_base_url or "http://localhost:11434"
    ollama_key = (body.ollama_api_key if body else None) or _get_secret_value(settings.ollama_api_key)
    openai_key = (body.openai_api_key if body else None) or _get_secret_value(settings.openai_api_key)

    if provider == "ollama":
        headers = {}
        if ollama_key:
            headers["Authorization"] = f"Bearer {ollama_key}"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                is_local = any(
                    ollama_base_url.startswith(p)
                    for p in ("http://localhost", "http://127.0.0.1", "http://::1")
                )
                endpoint = "/api/tags" if is_local else "/models"
                resp = await client.get(f"{ollama_base_url.rstrip('/')}{endpoint}", headers=headers)
                resp.raise_for_status()
                data = resp.json()
                if is_local:
                    return ListModelsResponse(models=[m["name"] for m in data.get("models", [])])
                return ListModelsResponse(models=[m["id"] for m in data.get("data", [])])
        except httpx.TimeoutException:
            return ListModelsResponse(models=[])
        except Exception:
            return ListModelsResponse(models=[])

    if provider == "openai":
        if not openai_key:
            return ListModelsResponse(models=[])
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {openai_key}"},
                )
                resp.raise_for_status()
                data = resp.json()
                return ListModelsResponse(models=[m["id"] for m in data.get("data", [])])
        except Exception:
            return ListModelsResponse(models=[])

    return ListModelsResponse(models=[])
