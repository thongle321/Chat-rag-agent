from fastapi import APIRouter
from app.api import auth, chat, docs, facebook, health, sessions, settings, stats

router = APIRouter(prefix="/api")

# Health check (public, no auth required)
router.include_router(auth.router, prefix="/auth", tags=["auth"])

router.include_router(health.router, prefix="/health", tags=["health"])

# Settings
router.include_router(settings.router, prefix="/settings", tags=["settings"])

# Stats
router.include_router(stats.router, prefix="/stats", tags=["stats"])

# Existing routes
router.include_router(docs.router, prefix="/documents", tags=["documents"])
router.include_router(chat.router, prefix="/chat", tags=["chat"])
router.include_router(sessions.router, prefix="/chat", tags=["chat"])

# Facebook Messenger (webhook + config)
router.include_router(facebook.router, prefix="/facebook", tags=["facebook"])
