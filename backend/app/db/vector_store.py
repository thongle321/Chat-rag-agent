from pathlib import Path

import chromadb

from app.core.config import settings
from app.db.embeddings import get_embeddings
import logging


logger = logging.getLogger(__name__)

# ChromaDB setup
persist_dir = Path(settings.vector_store_dir)
persist_dir.mkdir(parents=True, exist_ok=True)

chroma_client = chromadb.PersistentClient(path=str(persist_dir))
chroma_collection = chroma_client.get_or_create_collection(
    "documents",
    metadata={"hnsw:space": "cosine"},
)

embed_model = get_embeddings()

logger.info("Vector store initialized. Document count: %d", chroma_collection.count())


def query_similar(query_embedding: list[float], k: int = 5) -> list[dict]:
    """Query ChromaDB for similar documents. Returns list of {content, metadata, score}."""
    results = chroma_collection.query(
        query_embeddings=[query_embedding],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )
    out = []
    if not results["ids"]:
        return out
    for i in range(len(results["ids"][0])):
        out.append({
            "content": results["documents"][0][i],
            "metadata": results["metadatas"][0][i] or {},
            "score": results["distances"][0][i],
        })
    return out


def document_count() -> int:
    """Return total number of chunks in the vector store."""
    return chroma_collection.count()


def list_documents() -> list[dict]:
    """List unique documents stored in the vector store, grouped by title."""
    result = chroma_collection.get(include=["metadatas"])
    if not result["ids"]:
        return []

    upload_dir = Path(settings.upload_dir)

    seen: dict[str, dict] = {}
    for doc_id, meta in zip(result["ids"], result["metadatas"]):
        title = meta.get("title", doc_id)
        if title not in seen:
            file_path = upload_dir / title
            size = file_path.stat().st_size if file_path.exists() else 0
            seen[title] = {
                "document_id": doc_id,
                "title": title,
                "chunks": 0,
                "size": size,
            }
        seen[title]["chunks"] += 1

    return list(seen.values())


def delete_document(title: str) -> int:
    """Delete all chunks for a document by title. Returns number of chunks deleted."""
    result = chroma_collection.get(
        where={"title": title},
        include=["metadatas"],
    )
    if not result["ids"]:
        return 0

    chroma_collection.delete(ids=result["ids"])
    logger.info("Deleted %d chunks for document '%s'", len(result["ids"]), title)
    return len(result["ids"])
