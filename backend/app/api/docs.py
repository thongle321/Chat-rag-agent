from fastapi import APIRouter, BackgroundTasks
from fastapi import UploadFile, File
from pathlib import Path
from app.models.schemas import DocumentIngestResponse, DocumentListResponse, DocumentInfo
from app.services.document_ingest import save_and_queue_indexing, _index_file
from app.db.vector_store import list_documents, delete_document
from app.core.config import settings
from app.utils.logger import get_logger
from app.services.user_manager import current_active_user
from app.models.user import User

logger = get_logger(__name__)

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
                document_id="",
                message=f"File {safe_name} exceeds 50 MB limit",
            ))
            continue
        saved, message, saved_path = await save_and_queue_indexing(safe_name, content)
        status = "ok" if saved else "error"
        if saved and saved_path:
            background_tasks.add_task(_index_file, saved_path)
        results.append(DocumentIngestResponse(
            status=status,
            document_id="",
            message=message,
        ))
    return {"results": results}


@router.get("", response_model=DocumentListResponse)
async def list_all_documents(user: User = current_active_user):
    docs = list_documents()
    return DocumentListResponse(documents=[DocumentInfo(**d) for d in docs])


@router.delete("/{title}")
async def delete_document_by_title(title: str, user: User = current_active_user):
    deleted = delete_document(title)
    upload_dir = Path(settings.upload_dir)
    for f in upload_dir.iterdir():
        if f.is_file() and f.stem == title:
            f.unlink()
            break
    return {"status": "deleted", "chunks_deleted": deleted}
