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


def rrf(ranked: list[list[str]], k: int = 60) -> list[str]:
    """Reciprocal Rank Fusion (Chroma RRF formula): score = sum(1 / (k + rank))."""
    scores: dict[str, float] = defaultdict(float)
    for lst in ranked:
        for rank, doc_id in enumerate(lst):
            scores[doc_id] += 1.0 / (k + rank + 1)
    return [i for i, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)]


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
        """BM25 lexical search fused with dense vector search via Reciprocal Rank Fusion.

        ponytail: rebuilds the BM25 index per call over the full collection — fine for ~50 chunks,
        cache it (and update on add/delete) when the KB grows past a few thousand chunks.
        """
        if not query_text.strip():
            return self.query(query_embedding, k=k)

        all_docs = self._collection.get(include=["documents", "metadatas"])
        ids = all_docs["ids"]
        if not ids:
            return []

        # one merged EN+VI stopword list serves both languages
        corpus_tokens = bm25s.tokenize(all_docs["documents"], stopwords=_STOPWORDS, show_progress=False)
        # lucene idf is always positive — robertson clamps idf to 0 on tiny corpora (every term in >= N/2 docs)
        retriever = bm25s.BM25(method="lucene", k1=1.2, b=0.75)
        retriever.index(corpus_tokens, show_progress=False)
        hits, _ = retriever.retrieve(
            bm25s.tokenize(query_text, stopwords=_STOPWORDS, show_progress=False),
            k=k * 2,
            show_progress=False,
        )
        bm25_ranks = [ids[i] for i in hits[0]]
        vec_ranks = [d["id"] for d in self.query(query_embedding, k=k * 2)]

        fused = rrf([vec_ranks, bm25_ranks])[:k]
        doc_by_id = dict(zip(ids, all_docs["documents"]))
        meta_by_id = dict(zip(ids, all_docs["metadatas"]))
        return [
            {
                "id": doc_id,
                "content": doc_by_id.get(doc_id, ""),
                "metadata": meta_by_id.get(doc_id, {}),
                "score": 0.0,
            }
            for doc_id in fused
        ]

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


def _check() -> None:
    corpus = [
        "Nghị định này có hiệu lực thi hành kể từ ngày 25 tháng 5 năm 2026",
        "Các đơn vị sự nghiệp công lập thuộc bộ được tổ chức lại",
        "Thủ tướng Chính phủ quyết định danh sách các đơn vị",
    ]
    retriever = bm25s.BM25(method="lucene", k1=1.2, b=0.75)
    retriever.index(bm25s.tokenize(corpus, stopwords=_STOPWORDS, show_progress=False), show_progress=False)
    vi_query = "Nghị định có hiệu lực thi hành kể từ ngày nào"
    hits, _ = retriever.retrieve(
        bm25s.tokenize(vi_query, stopwords=_STOPWORDS, show_progress=False),
        k=1,
        show_progress=False,
    )
    assert corpus[hits[0, 0]] == corpus[0], f"BM25 exact-phrase rank wrong: {corpus[hits[0, 0]]}"

    en_corpus = [
        "The effective date of the decree is May 25 2026",
        "The Ministry of Culture is responsible for enforcement",
    ]
    en_retriever = bm25s.BM25(method="lucene", k1=1.2, b=0.75)
    en_retriever.index(bm25s.tokenize(en_corpus, stopwords=_STOPWORDS, show_progress=False), show_progress=False)
    en_query = "what is the effective date of the decree"
    en_hits, _ = en_retriever.retrieve(
        bm25s.tokenize(en_query, stopwords=_STOPWORDS, show_progress=False),
        k=1,
        show_progress=False,
    )
    assert en_corpus[en_hits[0, 0]] == en_corpus[0], "English BM25 top match wrong"

    fused = rrf([["a", "b", "c"], ["b", "d", "e"]])
    assert fused[0] == "b", f"RRF should rank doc in both lists first: {fused}"
    assert set(fused) == {"a", "b", "c", "d", "e"}, f"RRF dropped a doc: {fused}"

    print("vector_store hybrid check OK")


if __name__ == "__main__":
    _check()
