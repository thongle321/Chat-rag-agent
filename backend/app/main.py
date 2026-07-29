from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from app.core.config import settings
from app.core.middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from app.api.routes import router
from app.channels.facebook import close_client
from app.db.session import async_session_factory, create_db_and_tables
from app.services.rag import close_checkpointer, get_checkpointer
from app.services.seed import seed_admin_user


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.jwt_secret_key:
        raise RuntimeError("JWT_SECRET_KEY must be set via env var in production")

    await create_db_and_tables()
    await seed_admin_user()
    await get_checkpointer()

    async with async_session_factory() as session:
        from app.services.ai_settings import get_ai_settings
        db = await get_ai_settings(session)
        if db:
            settings.ai_provider = db["ai_provider"]
            settings.ollama_base_url = db["ollama_base_url"]
            settings.ollama_model = db["ollama_model"]
            settings.ollama_api_key = db["ollama_api_key"]
            settings.openai_model = db["openai_model"]
            settings.openai_api_key = db["openai_api_key"]

    yield

    await close_client()
    await close_checkpointer()


app = FastAPI(
    title=settings.app_name,
    description="FastAPI backend for ingesting documents, answering user questions, collecting feedback, and connecting Facebook.",
    version=settings.version,
    lifespan=lifespan,
)

# Add middleware (last added = first executed)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=60)
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
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
