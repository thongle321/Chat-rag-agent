import asyncio
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.db.vector_store import get_vector_store
from app.models.schemas import StatsResponse
from app.models.session import ChatSession
from app.services.rag import get_messages

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
async def get_stats(db: AsyncSession = Depends(get_async_session)):
    """Aggregate stats for the dashboard."""
    # Documents + chunks
    docs = await asyncio.to_thread(get_vector_store().list_documents)
    total_documents = len(docs)
    total_chunks = await asyncio.to_thread(get_vector_store().count)

    # Sessions
    result = await db.execute(select(func.count(ChatSession.id)))
    total_sessions = result.scalar() or 0

    # Total queries — sum message counts across recent sessions (bounded scan)
    total_queries = 0
    if total_sessions:
        session_result = await db.execute(
            select(ChatSession.id).order_by(ChatSession.updated_at.desc()).limit(500)
        )
        session_ids = [r[0] for r in session_result.all()]
        for sid in session_ids:
            try:
                msgs = await get_messages(sid)
                total_queries += sum(1 for m in msgs if m["role"] == "user")
            except Exception:
                logger.exception("Skipping corrupt conversation for stats: %s", sid)

    return StatsResponse(
        total_documents=total_documents,
        total_chunks=total_chunks,
        total_sessions=total_sessions,
        total_queries=total_queries,
    )
