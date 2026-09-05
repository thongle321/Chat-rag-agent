import secrets
from typing import Literal

import httpx2 as httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_async_session
from app.models.user import User
from app.services.ai_settings import save_ai_settings
from app.services.shopify_global import (
    DEFAULT_ENDPOINT,
    DEFAULT_PROFILE_URL,
    KEY_CATALOG_ID,
    KEY_ENABLED,
    KEY_ENDPOINT,
    KEY_PROFILE_URL,
    GlobalCatalogError,
    get_catalog_config,
    save_catalog_config,
    test_catalog,
)
from app.services.user_manager import current_admin_user


class AISettingsResponse(BaseModel):
    ai_provider: str
    ollama_base_url: str
    ollama_model: str
    ollama_api_key: str = ""
    openai_model: str
    openai_api_key: str = ""
    zalo_api_key: str = ""
    zalo_verify_token: str = ""
    zalo_webhook_url: str = ""


class AISettingsUpdate(BaseModel):
    ai_provider: Literal["ollama", "openai"] | None = None
    ollama_base_url: str | None = None
    ollama_model: str | None = None
    ollama_api_key: str | None = None
    openai_api_key: str | None = None
    openai_model: str | None = None
    zalo_api_key: str | None = None
    zalo_verify_token: str | None = None
    zalo_webhook_url: str | None = None
    zalo_regenerate: bool | None = None


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
async def get_ai_settings(user: User = current_admin_user):
    zalo_key = _get_secret_value(getattr(settings, "zalo_api_key", SecretStr("")))
    zalo_verify = _get_secret_value(getattr(settings, "zalo_verify_token", SecretStr("")))
    zalo_webhook = getattr(settings, "zalo_webhook_url", "")
    return AISettingsResponse(
        ai_provider=settings.ai_provider,
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
        ollama_api_key=_get_secret_value(settings.ollama_api_key),
        openai_model=settings.openai_model,
        openai_api_key=_get_secret_value(settings.openai_api_key),
        zalo_api_key=zalo_key,
        zalo_verify_token=zalo_verify,
        zalo_webhook_url=zalo_webhook,
    )


def _get_secret_value(v):
    return v.get_secret_value() if hasattr(v, 'get_secret_value') else v or ""


@router.put("/ai", response_model=AISettingsResponse)
async def update_ai_settings(
    body: AISettingsUpdate,
    user: User = current_admin_user,
    session: AsyncSession = Depends(get_async_session),
):
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

    # Zalo global key — one of the 3 integration inputs moved here so it never needs manual input per-bot.
    # We store verify_token (secret for webhook) globally; bot_token stays per-channel.
    zalo_key_val = _get_secret_value(getattr(settings, "zalo_api_key", SecretStr("")))
    zalo_verify_val = _get_secret_value(getattr(settings, "zalo_verify_token", SecretStr("")))
    zalo_webhook_val = getattr(settings, "zalo_webhook_url", "")
    if body.zalo_regenerate:
        zalo_verify_val = secrets.token_urlsafe(32)
        settings.zalo_verify_token = SecretStr(zalo_verify_val)
        zalo_key_val = zalo_verify_val  # keep legacy alias in sync
        settings.zalo_api_key = SecretStr(zalo_key_val)
    else:
        if body.zalo_verify_token is not None:
            zalo_verify_val = body.zalo_verify_token
            settings.zalo_verify_token = SecretStr(zalo_verify_val)
            zalo_key_val = zalo_verify_val
            settings.zalo_api_key = SecretStr(zalo_key_val)
        elif body.zalo_api_key is not None:
            zalo_verify_val = body.zalo_api_key
            zalo_key_val = body.zalo_api_key
            settings.zalo_verify_token = SecretStr(zalo_verify_val)
            settings.zalo_api_key = SecretStr(zalo_key_val)
        elif not zalo_verify_val:
            zalo_verify_val = secrets.token_urlsafe(32)
            settings.zalo_verify_token = SecretStr(zalo_verify_val)
            zalo_key_val = zalo_verify_val
            settings.zalo_api_key = SecretStr(zalo_key_val)
    if body.zalo_webhook_url is not None:
        zalo_webhook_val = body.zalo_webhook_url
        settings.zalo_webhook_url = zalo_webhook_val

    await save_ai_settings(session, {
        "ai_provider": settings.ai_provider,
        "ollama_base_url": settings.ollama_base_url,
        "ollama_model": settings.ollama_model,
        "ollama_api_key": _get_secret_value(settings.ollama_api_key),
        "openai_model": settings.openai_model,
        "openai_api_key": _get_secret_value(settings.openai_api_key),
        "zalo_api_key": zalo_key_val,
        "zalo_verify_token": zalo_verify_val,
        "zalo_webhook_url": zalo_webhook_val,
    })

    return AISettingsResponse(
        ai_provider=settings.ai_provider,
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
        ollama_api_key=_get_secret_value(settings.ollama_api_key),
        openai_model=settings.openai_model,
        openai_api_key=_get_secret_value(settings.openai_api_key),
        zalo_api_key=zalo_key_val,
        zalo_verify_token=zalo_verify_val,
        zalo_webhook_url=zalo_webhook_val,
    )


@router.post("/test", response_model=TestConnectionResponse)
async def test_connection(body: TestConnectionRequest, user: User = current_admin_user):
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
        except Exception:
            return TestConnectionResponse(ok=False, message="Ollama error: connection failed.")

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
                return TestConnectionResponse(ok=True, message="Connected to OpenAI.")
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            msg = "Invalid or expired OpenAI API key (401)." if code == 401 else f"OpenAI returned HTTP {code}."
            return TestConnectionResponse(ok=False, message=msg)
        except Exception:
            return TestConnectionResponse(ok=False, message="OpenAI error: connection failed.")

    return TestConnectionResponse(ok=False, message=f"Unknown provider '{provider}'.")


@router.post("/models", response_model=ListModelsResponse)
async def list_models(body: ListModelsRequest | None = None, user: User = current_admin_user):
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


class ShopifyCatalogResponse(BaseModel):
    enabled: bool
    endpoint: str
    profile_url: str
    catalog_id: str = ""


class ShopifyCatalogUpdate(BaseModel):
    enabled: bool | None = None
    endpoint: str | None = None
    profile_url: str | None = None
    catalog_id: str | None = None


@router.get("/shopify-catalog", response_model=ShopifyCatalogResponse)
async def get_shopify_catalog(user: User = current_admin_user, session: AsyncSession = Depends(get_async_session)):
    return ShopifyCatalogResponse(**await get_catalog_config(session))


@router.put("/shopify-catalog", response_model=ShopifyCatalogResponse)
async def update_shopify_catalog(
    body: ShopifyCatalogUpdate,
    user: User = current_admin_user,
    session: AsyncSession = Depends(get_async_session),
):
    data: dict = {}
    if body.enabled is not None:
        data[KEY_ENABLED] = "1" if body.enabled else "0"
    if body.endpoint is not None:
        data[KEY_ENDPOINT] = body.endpoint.strip() or DEFAULT_ENDPOINT
    if body.profile_url is not None:
        data[KEY_PROFILE_URL] = body.profile_url.strip() or DEFAULT_PROFILE_URL
    if body.catalog_id is not None:
        data[KEY_CATALOG_ID] = body.catalog_id.strip()
    return ShopifyCatalogResponse(**await save_catalog_config(session, data))


@router.post("/shopify-catalog/test", response_model=TestConnectionResponse)
async def test_shopify_catalog(user: User = current_admin_user, session: AsyncSession = Depends(get_async_session)):
    cfg = await get_catalog_config(session)
    try:
        await test_catalog(cfg["endpoint"], cfg["profile_url"])
        return TestConnectionResponse(ok=True, message="Catalog connected.")
    except GlobalCatalogError as e:
        return TestConnectionResponse(ok=False, message=str(e))
