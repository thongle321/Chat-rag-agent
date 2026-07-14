from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.middleware import RequestIDMiddleware, SecurityHeadersMiddleware
from app.core.exceptions import register_exception_handlers
from app.api.routes import router

app = FastAPI(
    title=settings.app_name,
    description="FastAPI backend for ingesting documents, answering user questions, collecting feedback, and connecting Facebook.",
    version=settings.version,
)

register_exception_handlers(app)

# Add middleware (last added = first executed)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
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
