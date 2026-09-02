from fastapi import APIRouter

from app.api import auth, chat, docs, facebook, health, logs, sessions, settings, stats, zalo

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
router.include_router(logs.router, prefix="/logs", tags=["logs"])

# Facebook Messenger (webhook + config)
router.include_router(facebook.router, prefix="/facebook", tags=["facebook"])
router.include_router(zalo.router, prefix="/zalo", tags=["zalo"])
