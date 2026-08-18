from pathlib import Path

from app.core.config import settings
from app.db.vector_store import get_vector_store


def list_documents() -> list[dict]:
    return get_vector_store().list_documents()


def document_count() -> int:
    return get_vector_store().count()


def delete_document(title: str) -> int:
    """Delete vector chunks and the uploaded file for a document."""
    deleted = get_vector_store().delete_document(title)
    upload_dir = Path(settings.upload_dir)
    for f in upload_dir.iterdir():
        if f.is_file() and f.name == title:
            f.unlink()
            break
    return deleted
