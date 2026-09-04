import logging
from functools import lru_cache

from app.core.config import settings
from app.db.embeddings import get_embeddings
from app.db.embeddings import passage_prefix as _passage_prefix
from app.db.embeddings import query_prefix as _query_prefix
from app.db.vector_store import get_vector_store
from app.db.vector_store import rrf as _rrf

logger = logging.getLogger(__name__)


class ChromaRetrieval:
    def search(self, query: str, k: int | None = None) -> list[dict]:
        """Hybrid search: dense over-retrieve + BM25 ranks fused via RRF, optional distance gate."""
        k = k or settings.retrieval_k
        q_emb = next(get_embeddings().query_embed(_query_prefix() + query))
        store = get_vector_store()
        if not query.strip():
            return store.query(q_emb, k=k)
        # over-retrieve for gate
        over = settings.retrieval_bm25_overretrieve
        vec_hits = store.query(q_emb, k=k * over)
        # keep distances for gate
        dist_by_id = {h["id"]: h["score"] for h in vec_hits}
        vec_ranks = [h["id"] for h in vec_hits]
        # bm25 ranks
        bm25_ranks = store.bm25_ranks(query, k=k * over)
        if not bm25_ranks:
            fused = [(h["id"], 1.0 / (settings.retrieval_rrf_k + i + 1)) for i, h in enumerate(vec_hits)]
        else:
            fused = _rrf([vec_ranks, bm25_ranks], k=settings.retrieval_rrf_k)
        fused = fused[: k * 2]
        # gate on cosine distance if enabled
        thr = settings.retrieval_distance_threshold
        if thr is not None:
            gated = [(doc_id, sc) for doc_id, sc in fused if dist_by_id.get(doc_id, 2.0) < thr]
            fused = gated[:k] if gated else []
        else:
            fused = fused[:k]
        if not fused:
            return []
        hydrated = {h["id"]: h for h in store.fetch([i for i, _ in fused])}
        out = []
        for doc_id, score in fused:
            h = hydrated.get(doc_id, {"content": "", "metadata": {}})
            out.append(
                {
                    "id": doc_id,
                    "content": h["content"],
                    "metadata": h["metadata"],
                    "score": score,
                    "distance": dist_by_id.get(doc_id),
                }
            )
        logger.info("retrieval q=%r k=%d fused=%d kept=%d thr=%s", query[:60], k, len(fused), len(out), thr)
        return out

    def ingest_embed(self, texts: list[str]) -> list[list[float]]:
        return list(get_embeddings().embed([_passage_prefix() + t for t in texts]))

    def list_documents(self) -> list[dict]:
        return get_vector_store().list_documents()

    def count(self) -> int:
        return get_vector_store().count()

    def delete_document(self, title: str) -> int:
        return get_vector_store().delete_document(title)

    def delete_document_and_file(self, title: str) -> int:
        return get_vector_store().delete_document_and_file(title)

    def get_metadata(self, ids: list[str]) -> dict[str, dict]:
        return get_vector_store().get_metadata(ids)

    def add(self, ids: list[str], embeddings: list[list[float]], documents: list[str], metadatas: list[dict]) -> None:
        return get_vector_store().add(ids, embeddings, documents, metadatas)


@lru_cache(maxsize=1)
def get_retrieval() -> ChromaRetrieval:
    return ChromaRetrieval()
