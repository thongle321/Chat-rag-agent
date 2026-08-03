import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import chromadb

from app.core.config import settings

logger = logging.getLogger(__name__)

persist_dir = Path(settings.vector_store_dir)
persist_dir.mkdir(parents=True, exist_ok=True)


class VectorStore(Protocol):
    """Boundary for vector similarity storage. Swap ChromaDB for another backend here."""

    def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None: ...

    def query(self, query_embedding: list[float], k: int = 5) -> list[dict]: ...

    def count(self) -> int: ...

    def list_documents(self) -> list[dict]: ...

    def delete_document(self, title: str) -> int: ...


class ChromaVectorStore:
    def __init__(self) -> None:
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection = self._client.get_or_create_collection(
            "documents",
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "Vector store initialized. Document count: %d", self._collection.count()
        )

    def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        self._collection.add(
            ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
        )

    def query(self, query_embedding: list[float], k: int = 5) -> list[dict]:
        """Return list of {content, metadata, score} for the k nearest chunks."""
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )
        out = []
        if not results["ids"]:
            return out
        for i in range(len(results["ids"][0])):
            out.append(
                {
                    "content": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i] or {},
                    "score": results["distances"][0][i],
                }
            )
        return out

    def count(self) -> int:
        return self._collection.count()

    def list_documents(self) -> list[dict]:
        """List unique documents grouped by title."""
        result = self._collection.get(include=["metadatas"])
        if not result["ids"]:
            return []

        upload_dir = Path(settings.upload_dir)
        seen: dict[str, dict[str, Any]] = {}
        for doc_id, meta in zip(result["ids"], result["metadatas"]):
            title = meta.get("title", doc_id)
            if title not in seen:
                file_path = upload_dir / title
                size = file_path.stat().st_size if file_path.exists() else 0
                seen[title] = {
                    "document_id": doc_id,
                    "title": title,
                    "summary": meta.get("summary", ""),
                    "chunks": 0,
                    "size": size,
                }
            seen[title]["chunks"] += 1

        return list(seen.values())

    def delete_document(self, title: str) -> int:
        """Delete all chunks for a document by title. Returns number of chunks deleted."""
        result = self._collection.get(where={"title": title}, include=["metadatas"])
        if not result["ids"]:
            return 0

        self._collection.delete(ids=result["ids"])
        logger.info("Deleted %d chunks for document '%s'", len(result["ids"]), title)
        return len(result["ids"])


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    return ChromaVectorStore()
