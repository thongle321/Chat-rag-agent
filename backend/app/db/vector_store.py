import json
import logging
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

import bm25s
import chromadb
from bm25s.tokenization import STOPWORDS_EN

from app.core.config import settings

logger = logging.getLogger(__name__)

persist_dir = Path(settings.vector_store_dir)
persist_dir.mkdir(parents=True, exist_ok=True)




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
    def __init__(self, collection_name: str = "documents", bm25_subdir: str = "bm25_index") -> None:
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection = self._client.get_or_create_collection(
            collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._bm25: bm25s.BM25 | None = None
        self._bm25_ids: list[str] | None = None
        self._bm25_dir = Path(settings.upload_dir).resolve().parent / bm25_subdir
        logger.info("Vector store '%s' initialized. Count: %d", collection_name, self._collection.count())

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
        self._collection.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
        self._invalidate_bm25()

    def upsert(
        self, ids: list[str], embeddings: list[list[float]], documents: list[str], metadatas: list[dict]
    ) -> None:
        self._collection.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
        self._invalidate_bm25()

    def delete_ids(self, ids: list[str]) -> None:
        """Delete chunks by id (missing ids are ignored)."""
        if not ids:
            return
        self._collection.delete(ids=ids)
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

    def bm25_ranks(self, query_text: str, k: int) -> list[str]:
        """Top-k chunk ids by lexical (BM25) rank. Empty when the index is empty."""
        ids = self._ensure_bm25()
        if not ids or not query_text.strip():
            return []
        hits, _ = self._bm25.retrieve(
            bm25s.tokenize(query_text, stopwords=_STOPWORDS, show_progress=False),
            k=min(k, len(ids)),  # bm25s raises when k > corpus size
            show_progress=False,
        )
        return [ids[i] for i in hits[0]]

    def fetch(self, ids: list[str]) -> list[dict]:
        """Hydrate [{id, content, metadata}] for chunk ids (missing ids are omitted)."""
        if not ids:
            return []
        res = self._collection.get(ids=ids, include=["documents", "metadatas"])
        return [
            {"id": i, "content": d or "", "metadata": m or {}}
            for i, d, m in zip(res["ids"], res["documents"], res["metadatas"], strict=True)
        ]

    def get_metadata(self, ids: list[str]) -> dict[str, dict]:
        """Return {id: metadata} for the given chunk ids (missing ids are omitted)."""
        if not ids:
            return {}
        res = self._collection.get(ids=ids, include=["metadatas"])
        return {i: (m or {}) for i, m in zip(res["ids"], res["metadatas"], strict=False)}

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
            # title (filename) is the identity used for status polling, size lookup, and delete;
            # clean_title is the LLM name shown in chat citations only.
            title = meta.get("title") or doc_id
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

    def delete_document_and_file(self, title: str) -> int:
        deleted = self.delete_document(title)
        (Path(settings.upload_dir) / title).unlink(missing_ok=True)
        return deleted


@lru_cache(maxsize=1)
def get_vector_store() -> ChromaVectorStore:
    return ChromaVectorStore()


@lru_cache(maxsize=1)
def get_product_store() -> ChromaVectorStore:
    """Separate collection for catalog products (own BM25, no cross-talk with documents)."""
    return ChromaVectorStore(collection_name="products", bm25_subdir="bm25_products")
