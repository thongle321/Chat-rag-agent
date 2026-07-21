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


class LazyEmbeddings:
    """Proxy around get_embeddings() that defers loading the embedding
    model until it is actually needed (i.e. on first embed call), rather
    than at module import / application startup time.
    """

    def embed_documents(self, texts):
        return get_embeddings().embed_documents(texts)

    def embed_query(self, text):
        return get_embeddings().embed_query(text)


# LangChain Chroma vector store. The embedding model itself is not loaded
# here - `embed_model` is a lazy proxy so the underlying HuggingFace model
# only downloads/loads on first actual use (e.g. first upload or chat
# request), keeping application startup fast.
embed_model = LazyEmbeddings()
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
    result = chroma_collection.get(
        where={"title": title},
        include=["metadatas"],
    )
    if not result["ids"]:
        return 0

    chroma_collection.delete(ids=result["ids"])
    logger.info("Deleted %d chunks for document '%s'", len(result["ids"]), title)
    return len(result["ids"])
