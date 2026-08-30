from fastapi import APIRouter

from app.core.config import settings
from app.db.vector_store import get_vector_store

router = APIRouter()


@router.get("")
async def health_check():
    """Basic health check endpoint."""
    return {
        "status": "ok",
        "version": settings.version,
        "environment": settings.environment,
    }


@router.get("/detailed")
async def detailed_health_check():
    """Detailed health check with component status."""
    health = {
        "status": "ok",
        "version": settings.version,
        "environment": settings.environment,
        "components": {},
    }

    try:
        count = get_vector_store().count()
        health["components"]["vector_store"] = "ok"
        health["components"]["vector_store_count"] = count
    except Exception:
        health["components"]["vector_store"] = "error"
        health["status"] = "degraded"

    return health
