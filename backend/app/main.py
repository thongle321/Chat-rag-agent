import secrets
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from app.core.config import settings
from app.core.middleware import RateLimitMiddleware, RequestIDMiddleware, SecurityHeadersMiddleware
from app.api.routes import router
from app.channels.facebook import close_client
from app.db.session import create_db_and_tables
from app.services.rag import close_checkpointer, get_checkpointer
from app.services.seed import seed_admin_user

app = FastAPI(
    title=settings.app_name,
    description="FastAPI backend for ingesting documents, answering user questions, collecting feedback, and connecting Facebook.",
    version=settings.version,
)

# Add middleware (last added = first executed)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=60)
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
async def startup():
    # Generate JWT secret if not set
    if not settings.jwt_secret_key:
        secret_path = Path(settings.upload_dir).resolve().parent / ".jwt_secret"
        if secret_path.exists():
            settings.jwt_secret_key = secret_path.read_text().strip()
        else:
            settings.jwt_secret_key = secrets.token_urlsafe(32)
            secret_path.write_text(settings.jwt_secret_key)

    # Create DB tables and seed admin user
    await create_db_and_tables()
    await seed_admin_user()

    # Initialize LangGraph checkpointer for chat sessions
    await get_checkpointer()


@app.on_event("shutdown")
async def shutdown():
    await close_client()
    await close_checkpointer()


@app.get("/")
def root():
    return {
        "message": "Welcome to the Document RAG Chatbot backend.",
        "environment": settings.environment,
        "version": settings.version,
    }
