import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, Request, UploadFile

from app.db.vector_store import get_vector_store
from app.models.schemas import DocumentInfo, DocumentIngestResponse, DocumentListResponse
from app.models.user import User
from app.services.chat_logging import log_activity
from app.services.document_ingest import index_file, save_and_queue_indexing
from app.services.document_status import get_document_statuses, normalize_status
from app.services.user_manager import current_active_user

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB


@router.post("/upload")
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    user: User = current_active_user,
):
    """Upload one or more document files. Files are saved and indexed in background."""
    ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()[:45]
        if request.headers.get("x-forwarded-for")
        else (str(request.client.host)[:45] if request.client else None)
    )
    results = []
    for file in files:
        safe_name = Path(file.filename).name if file.filename else "unnamed"
        content = await file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            results.append(
                DocumentIngestResponse(
                    status="error",
                    message=f"File {safe_name} exceeds 50 MB limit",
                )
            )
            await log_activity(
                action="document.upload",
                user_id=str(user.id),
                user_email=user.email,
                resource_type="document",
                resource_id=safe_name,
                detail="rejected: exceeds 50MB",
                ip_address=ip,
            )
            continue
        message, saved_path = await save_and_queue_indexing(safe_name, content)
        background_tasks.add_task(index_file, saved_path)
        results.append(
            DocumentIngestResponse(
                status="ok",
                message=message,
            )
        )
        await log_activity(
            action="document.upload",
            user_id=str(user.id),
            user_email=user.email,
            resource_type="document",
            resource_id=safe_name,
            detail=message,
            ip_address=ip,
        )
    return {"results": results}


@router.get("", response_model=DocumentListResponse)
async def list_all_documents(user: User = current_active_user):
    docs = await asyncio.to_thread(get_vector_store().list_documents)
    return DocumentListResponse(documents=[DocumentInfo.model_validate(d) for d in docs])


@router.delete("/{title}")
async def delete_document_by_title(request: Request, title: str, user: User = current_active_user):
    deleted = await asyncio.to_thread(get_vector_store().delete_document_and_file, title)
    ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()[:45]
        if request.headers.get("x-forwarded-for")
        else (str(request.client.host)[:45] if request.client else None)
    )
    await log_activity(
        action="document.delete",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="document",
        resource_id=title,
        detail=f"chunks_deleted={deleted}",
        ip_address=ip,
    )
    return {"status": "deleted", "chunks_deleted": deleted}


async def _build_status_results(titles: list[str]) -> dict:
    existing = await asyncio.to_thread(get_vector_store().list_documents)
    existing_map = {d["title"]: d for d in existing}
    statuses = await get_document_statuses(titles)
    results = {}
    for title in titles:
        st = statuses.get(title) or {}
        results[title] = {
            "status": normalize_status(st.get("status")),
            "chunks": st.get("chunks", 0),
            "size": existing_map.get(title, {}).get("size", 0),
            "error_message": st.get("error_message"),
        }
    return results


@router.get("/upload/status")
async def poll_upload_status(titles: str = Query(...), user: User = current_active_user):
    """Return indexing status; the frontend polls this every few seconds."""
    title_list = [t.strip() for t in titles.split(",") if t.strip()]
    if not title_list:
        raise HTTPException(status_code=400, detail="No titles provided")
    results = await _build_status_results(title_list)
    return {"results": results}
