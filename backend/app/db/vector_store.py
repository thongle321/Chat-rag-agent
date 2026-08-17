import json
import logging
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import bm25s
import chromadb
from bm25s.tokenization import STOPWORDS_EN

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

    def hybrid_query(self, query_text: str, query_embedding: list[float], k: int = 5) -> list[dict]: ...

    def count(self) -> int: ...

    def list_documents(self) -> list[dict]: ...

    def delete_document(self, title: str) -> int: ...


# ported from MacPhuPhong/TRAFFIC_LAW_LLM_RAG_AGENTIC — hand-curated Vietnamese stopwords.
# Merged with bm25s English stopwords so one list serves both languages (each language's text
# only contains its own stopwords, so stripping both sets is harmless to the other).
_VI_STOPWORDS = [
    "là", "và", "của", "cho", "các", "có", "được", "trong", "theo",
    "với", "một", "khi", "hoặc", "từ", "này", "đó", "tại", "do",
    "để", "sẽ", "đã", "nếu", "bị", "bởi",
]
_STOPWORDS = list(STOPWORDS_EN) + _VI_STOPWORDS


def rrf(ranked: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion (Chroma RRF formula): score = sum(1 / (k + rank)).

    Returns (doc_id, score) pairs sorted by score desc.
    """
    scores: dict[str, float] = defaultdict(float)
    for lst in ranked:
        for rank, doc_id in enumerate(lst):
            scores[doc_id] += 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


class ChromaVectorStore:
    def __init__(self) -> None:
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection = self._client.get_or_create_collection(
            "documents",
            metadata={"hnsw:space": "cosine"},
        )
        self._bm25: bm25s.BM25 | None = None
        self._bm25_ids: list[str] | None = None
        self._bm25_dir = Path(settings.upload_dir).resolve().parent / "bm25_index"
        logger.info(
            "Vector store initialized. Document count: %d", self._collection.count()
        )

    def _invalidate_bm25(self) -> None:
        self._bm25 = None
        self._bm25_ids = None

    def _ensure_bm25(self) -> list[str]:
        """Return chroma ids aligned to the cached/persisted BM25 index, building it if stale.

        ponytail: no lock — a single uvicorn worker builds once; add a threading.Lock()
        in _ensure_bm25 only if concurrent first queries / multi-worker deploy becomes a thing.
        """
        ids = self._collection.get(include=[])["ids"]
        if self._bm25 is not None and self._bm25_ids == ids:
            return ids

        id_file = self._bm25_dir / "bm25_ids.json"
        if id_file.exists() and json.loads(id_file.read_text()) == ids:
            self._bm25 = bm25s.BM25.load(str(self._bm25_dir), load_vocab=True, show_progress=False)
        else:
            res = self._collection.get(include=["documents"])
            retriever = bm25s.BM25(method="lucene", k1=1.2, b=0.75)
            retriever.index(
                bm25s.tokenize(res["documents"], stopwords=_STOPWORDS, show_progress=False),
                show_progress=False,
            )
            self._bm25_dir.mkdir(parents=True, exist_ok=True)
            retriever.save(str(self._bm25_dir), show_progress=False)
            id_file.write_text(json.dumps(ids))
            self._bm25 = retriever
        self._bm25_ids = ids
        return ids

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
        self._invalidate_bm25()

    def query(self, query_embedding: list[float], k: int = 5) -> list[dict]:
        """Return list of {id, content, metadata, score} for the k nearest chunks."""
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
                    "id": results["ids"][0][i],
                    "content": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i] or {},
                    "score": results["distances"][0][i],
                }
            )
        return out

    def hybrid_query(self, query_text: str, query_embedding: list[float], k: int = 5) -> list[dict]:
        """BM25 lexical search fused with dense vector search via Reciprocal Rank Fusion."""
        if not query_text.strip():
            return self.query(query_embedding, k=k)

        ids = self._ensure_bm25()
        if not ids:
            return []

        hits, _ = self._bm25.retrieve(
            bm25s.tokenize(query_text, stopwords=_STOPWORDS, show_progress=False),
            k=k * 2,
            show_progress=False,
        )
        bm25_ranks = [ids[i] for i in hits[0]]
        vec_ranks = [d["id"] for d in self.query(query_embedding, k=k * 2)]

        fused = rrf([vec_ranks, bm25_ranks])[:k]
        res = self._collection.get(ids=[i for i, _ in fused], include=["documents", "metadatas"])
        doc_by_id = dict(zip(res["ids"], res["documents"], strict=True))
        meta_by_id = dict(zip(res["ids"], res["metadatas"], strict=True))
        return [
            {
                "id": doc_id,
                "content": doc_by_id.get(doc_id, ""),
                "metadata": meta_by_id.get(doc_id, {}),
                "score": score,
            }
            for doc_id, score in fused
        ]

    def count(self) -> int:
        return self._collection.count()

    def list_documents(self) -> list[dict]:
        """List unique documents with clean_title and reference when available."""
        result = self._collection.get(include=["metadatas"])
        if not result["ids"]:
            return []

        upload_dir = Path(settings.upload_dir)
        seen: dict[str, dict[str, Any]] = {}
        for doc_id, meta in zip(result["ids"], result["metadatas"], strict=True):
            # Prefer clean_title for display; fall back to title (filename) for identity ops
            title = meta.get("clean_title") or meta.get("title") or doc_id
            if title not in seen:
                # Only use title as file path if it looks like a stored filename
                file_path = upload_dir / title if title and title != "document" and "/" not in title and "." in title else upload_dir / doc_id
                size = file_path.stat().st_size if file_path.exists() else 0
                seen[title] = {
                    "document_id": doc_id,
                    "title": title,
                    "clean_title": meta.get("clean_title"),
                    "summary": meta.get("summary", ""),
                    "reference": meta.get("reference"),
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
        self._invalidate_bm25()
        logger.info("Deleted %d chunks for document '%s'", len(result["ids"]), title)
        return len(result["ids"])


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    return ChromaVectorStore()
