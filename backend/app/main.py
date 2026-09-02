import logging
from contextlib import asynccontextmanager

import logfire
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi_users.password import PasswordHelper
from sqlalchemy import select
from starlette.types import Receive, Scope, Send

from app.api.facebook import close_client
from app.api.routes import router
from app.core.config import settings
from app.core.middleware import SecurityHeadersMiddleware
from app.db.session import async_session_factory, create_db_and_tables, engine
from app.models.user import User
# Import so Base.metadata includes new log tables for create_db_and_tables()
import app.models.chat_logging  # noqa: F401
from app.services.ai_settings import get_ai_settings
from app.services.rag import close


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.jwt_secret_key:
        raise RuntimeError("JWT_SECRET_KEY must be set via env var in production")

    logfire.configure(
        service_name="chat-rag-agent",
        token=settings.logfire_token.get_secret_value() if settings.logfire_token else None,
    )
    logfire.instrument_pydantic_ai()
    logfire.instrument_fastapi(app)
    logfire.instrument_httpx()
    logfire.instrument_sqlalchemy()
    logging.basicConfig(handlers=[logfire.LogfireLoggingHandler()], force=True)

    await create_db_and_tables()

    async with async_session_factory() as session:
        db = await get_ai_settings(session)
        if db:
            settings.ai_provider = db["ai_provider"]
            settings.ollama_base_url = db["ollama_base_url"]
            settings.ollama_model = db["ollama_model"]
            settings.ollama_api_key = db["ollama_api_key"]
            settings.openai_model = db["openai_model"]
            settings.openai_api_key = db["openai_api_key"]
            if db.get("zalo_api_key"):
                from pydantic import SecretStr as _SecretStr
                settings.zalo_api_key = _SecretStr(db["zalo_api_key"])
            if db.get("zalo_verify_token"):
                from pydantic import SecretStr as _SecretStr2
                settings.zalo_verify_token = _SecretStr2(db["zalo_verify_token"])
            elif db.get("zalo_api_key"):
                from pydantic import SecretStr as _SecretStr3
                settings.zalo_verify_token = _SecretStr3(db["zalo_api_key"])
            if db.get("zalo_webhook_url"):
                settings.zalo_webhook_url = db["zalo_webhook_url"]
        result = await session.execute(select(User).where(User.email == "admin@example.com"))
        if not result.scalar_one_or_none():
            hashed = PasswordHelper().hash("admin123")
            admin = User(
                email="admin@example.com",
                hashed_password=hashed,
                role="admin",
                is_active=True,
                is_superuser=True,
                is_verified=True,
            )
            session.add(admin)
            await session.commit()

    yield

    # --- Shutdown: close all persistent resources ---
    await close()
    await engine.dispose()
    await close_client()


app = FastAPI(
    title=settings.app_name,
    description=(
        "FastAPI backend for ingesting documents, answering user questions, "
        "collecting feedback, and connecting Facebook."
    ),
    version=settings.version,
    lifespan=lifespan,
)


class NoGzipForSSE(GZipMiddleware):
    """Bypass GZip for the chat SSE stream so tokens stream chunk-by-chunk."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] == "/api/chat/query/stream":
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


# Add middleware (last added = first executed)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(NoGzipForSSE, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def root():
    return {
        "message": "Welcome to the Document RAG Chatbot backend.",
        "environment": settings.environment,
        "version": settings.version,
    }
