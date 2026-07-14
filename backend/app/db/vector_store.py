from pathlib import Path

import chromadb
from langchain_chroma import Chroma

from app.core.config import settings
from app.db.embeddings import get_embeddings
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ChromaDB setup
persist_dir = Path(settings.vector_store_dir)
persist_dir.mkdir(parents=True, exist_ok=True)

chroma_client = chromadb.PersistentClient(path=str(persist_dir))
chroma_collection = chroma_client.get_or_create_collection(
    "documents",
    metadata={"hnsw:space": "cosine"},
)

# LangChain Chroma vector store
embed_model = get_embeddings()
vector_store = Chroma(
    client=chroma_client,
    collection_name="documents",
    embedding_function=embed_model,
)

logger.info("Vector store initialized. Document count: %d", chroma_collection.count())


def document_count() -> int:
    """Return total number of chunks in the vector store."""
    return chroma_collection.count()


def list_documents() -> list[dict]:
    """List unique documents stored in the vector store, grouped by title."""
    result = chroma_collection.get(include=["metadatas"])
    if not result["ids"]:
        return []

    seen: dict[str, dict] = {}
    for doc_id, meta in zip(result["ids"], result["metadatas"]):
        title = meta.get("title", doc_id)
        if title not in seen:
            seen[title] = {
                "document_id": doc_id,
                "title": title,
                "chunks": 0,
            }
        seen[title]["chunks"] += 1

    return list(seen.values())


def delete_document(title: str) -> int:
    """Delete all chunks for a document by title. Returns number of chunks deleted."""
    result = chroma_collection.get(include=["metadatas"])
    if not result["ids"]:
        return 0

    ids_to_delete = [
        doc_id
        for doc_id, meta in zip(result["ids"], result["metadatas"])
        if meta.get("title") == title
    ]

    if ids_to_delete:
        chroma_collection.delete(ids=ids_to_delete)
        logger.info("Deleted %d chunks for document '%s'", len(ids_to_delete), title)

    return len(ids_to_delete)
