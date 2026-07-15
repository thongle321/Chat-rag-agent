from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from app.core.config import settings
from app.core.middleware import RateLimitMiddleware, RequestIDMiddleware, SecurityHeadersMiddleware
from app.core.exceptions import register_exception_handlers
from app.api.routes import router
from app.channels.facebook import close_client

app = FastAPI(
    title=settings.app_name,
    description="FastAPI backend for ingesting documents, answering user questions, collecting feedback, and connecting Facebook.",
    version=settings.version,
)

register_exception_handlers(app)

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


@app.on_event("shutdown")
async def shutdown():
    await close_client()


@app.get("/")
def root():
    return {
        "message": "Welcome to the Document RAG Chatbot backend.",
        "environment": settings.environment,
        "version": settings.version,
    }
