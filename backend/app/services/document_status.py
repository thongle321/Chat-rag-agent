import logging

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.session import async_session_factory
from app.models.document_status import COMPLETED, FAILED, PENDING, PROCESSING, DocumentStatus

logger = logging.getLogger(__name__)


async def set_document_status(
    filename: str,
    *,
    status: str,
    chunk_count: int | None = None,
    error_message: str | None = None,
) -> None:
    """Upsert the ingestion status row for a document (pend->process->complete|fail)."""
    values = {"filename": filename, "status": status}
    if chunk_count is not None:
        values["chunk_count"] = chunk_count
    if error_message is not None:
        values["error_message"] = error_message

    stmt = sqlite_insert(DocumentStatus).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[DocumentStatus.filename],
        set_={
            "status": stmt.excluded.status,
            "chunk_count": stmt.excluded.chunk_count,
            "error_message": stmt.excluded.error_message,
        },
    )
    try:
        async with async_session_factory() as session:
            await session.execute(stmt)
            await session.commit()
    except Exception:
        logger.exception("Failed to update status for %s -> %s", filename, status)


async def get_document_statuses(filenames: list[str]) -> dict[str, dict]:
    """Return {filename: {status, chunks, error_message}} for the given filenames."""
    if not filenames:
        return {}
    try:
        async with async_session_factory() as session:
            rows = await session.execute(
                select(DocumentStatus).where(DocumentStatus.filename.in_(filenames))
            )
            return {
                db.filename: {
                    "status": db.status,
                    "chunks": db.chunk_count,
                    "error_message": db.error_message,
                }
                for db in rows.scalars()
            }
    except Exception:
        logger.exception("Failed to read document statuses")
        return {}


def normalize_status(status: str | None) -> str:
    """Default to pending for files queued but not yet visible in the status table."""
    if status not in (PENDING, PROCESSING, COMPLETED, FAILED):
        return PENDING
    return status