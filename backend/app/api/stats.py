from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.db.vector_store import document_count, list_documents
from app.models.session import ChatSession
from app.services.rag import get_messages

router = APIRouter()


@router.get("")
async def get_stats(db: AsyncSession = Depends(get_async_session)):
    """Aggregate stats for the dashboard."""
    # Documents + chunks
    docs = list_documents()
    total_documents = len(docs)
    total_chunks = document_count()

    # Sessions
    result = await db.execute(select(func.count(ChatSession.id)))
    total_sessions = result.scalar() or 0

    # Total queries — sum message counts across all sessions
    total_queries = 0
    if total_sessions:
        session_result = await db.execute(select(ChatSession.id))
        session_ids = [r[0] for r in session_result.all()]
        for sid in session_ids:
            msgs = await get_messages(sid)
            # Count user messages only
            total_queries += sum(1 for m in msgs if m["role"] == "user")

    return {
        "total_documents": total_documents,
        "total_chunks": total_chunks,
        "total_sessions": total_sessions,
        "total_queries": total_queries,
    }
