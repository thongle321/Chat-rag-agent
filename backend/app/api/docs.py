from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi import UploadFile, File
from pathlib import Path
from app.models.schemas import DocumentIngestResponse, DocumentListResponse, DocumentInfo
from app.services.document_ingest import save_and_queue_indexing, index_all_files_background
from app.db.vector_store import list_documents, delete_document
from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.post("/upload")
async def upload_files(
    files: list[UploadFile] = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Upload one or more document files. Files are saved and indexed in background."""
    results = []
    for file in files:
        content = await file.read()
        saved, message = await save_and_queue_indexing(file.filename, content)
        status = "ok" if saved else "error"
        if saved:
            background_tasks.add_task(index_all_files_background)
        results.append(DocumentIngestResponse(
            status=status,
            document_id="",
            message=message,
        ))
    return {"results": results}


@router.get("", response_model=DocumentListResponse)
async def list_all_documents():
    """List all indexed documents from the vector store."""
    try:
        docs = list_documents()
        return DocumentListResponse(
            documents=[DocumentInfo(**d) for d in docs]
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/{title}")
async def delete_document_by_title(title: str):
    """Delete a document and its chunks by title."""
    try:
        deleted = delete_document(title)

        upload_dir = Path(settings.upload_dir)
        for f in upload_dir.iterdir():
            if f.is_file() and f.stem == title:
                f.unlink()
                break

        return {"status": "deleted", "chunks_deleted": deleted}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
