import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile

from app.models.schemas import DocumentInfo, DocumentIngestResponse, DocumentListResponse
from app.models.user import User
from app.services import documents
from app.services.document_ingest import index_file, save_and_queue_indexing
from app.services.user_manager import current_active_user

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB


@router.post("/upload")
async def upload_files(
    files: list[UploadFile] = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    user: User = current_active_user,
):
    """Upload one or more document files. Files are saved and indexed in background."""
    results = []
    for file in files:
        safe_name = Path(file.filename).name if file.filename else "unnamed"
        content = await file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            results.append(DocumentIngestResponse(
                status="error",
                message=f"File {safe_name} exceeds 50 MB limit",
            ))
            continue
        message, saved_path = await save_and_queue_indexing(safe_name, content)
        background_tasks.add_task(index_file, saved_path)
        results.append(DocumentIngestResponse(
            status="ok",
            message=message,
        ))
    return {"results": results}


@router.get("", response_model=DocumentListResponse)
async def list_all_documents(user: User = current_active_user):
    docs = documents.list_documents()
    return DocumentListResponse(documents=[DocumentInfo.model_validate(d) for d in docs])


@router.delete("/{title}")
async def delete_document_by_title(title: str, user: User = current_active_user):
    deleted = documents.delete_document(title)
    return {"status": "deleted", "chunks_deleted": deleted}


def _build_status_results(titles: list[str]) -> dict:
    existing = documents.list_documents()
    existing_map = {d["title"]: d for d in existing}
    results = {}
    for title in titles:
        if title in existing_map:
            doc = existing_map[title]
            results[title] = {
                "status": "completed", "chunks": doc["chunks"], "size": doc["size"],
            }
        else:
            results[title] = {"status": "indexed", "chunks": 0, "size": 0}
    return results


@router.get("/upload/status")
async def poll_upload_status(titles: str = Query(...), user: User = current_active_user):
    """Return indexing status; the frontend polls this every few seconds."""
    title_list = [t.strip() for t in titles.split(",") if t.strip()]
    if not title_list:
        raise HTTPException(status_code=400, detail="No titles provided")
    return {"results": _build_status_results(title_list)}
