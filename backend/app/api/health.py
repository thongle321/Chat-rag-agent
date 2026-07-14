from fastapi import APIRouter

from app.core.config import settings

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
        from app.db.vector_store import document_count
        count = document_count()
        health["components"]["vector_store"] = "ok"
        health["components"]["vector_store_count"] = count
    except Exception:
        health["components"]["vector_store"] = "error"
        health["status"] = "degraded"

    return health
