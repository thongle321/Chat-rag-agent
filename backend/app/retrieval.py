import logging
from functools import lru_cache

from app.core.config import settings
from app.db.embeddings import get_embeddings
from app.db.embeddings import passage_prefix as _passage_prefix
from app.db.embeddings import query_prefix as _query_prefix
from app.db.vector_store import ChromaVectorStore, get_vector_store
from app.db.vector_store import fuse_ranks as _fuse

logger = logging.getLogger(__name__)


def hybrid_rank(
    store: ChromaVectorStore,
    query: str,
    q_emb: list[float],
    k: int,
    *,
    where: dict | None = None,
    gate: float | None = None,
    pre_gate_slice: int | None = None,
) -> list[tuple[str, float, float | None]]:
    """One hybrid sequence shared by every local collection.

    Dense over-retrieve (with optional `where` pre-fusion filter) + BM25 ranks
    fused via RRF, then an optional cosine-distance `gate`. Returns
    (doc_id, fusion_score, distance) in rank order — callers hydrate + shape.
    Blocking (Chroma/BM25): callers offload via asyncio.to_thread.
    """
    over = settings.retrieval_bm25_overretrieve
    vec_hits = store.query(q_emb, k * over, where)
    dist_by_id = {h["id"]: h["score"] for h in vec_hits}
    fused = _fuse([h["id"] for h in vec_hits], store.bm25_ranks(query, k * over), k=settings.retrieval_rrf_k)
    if pre_gate_slice is not None:
        fused = fused[:pre_gate_slice]
    if gate is not None:
        fused = [(doc_id, sc) for doc_id, sc in fused if dist_by_id.get(doc_id, 2.0) < gate]
    return [(doc_id, sc, dist_by_id.get(doc_id)) for doc_id, sc in fused]


class ChromaRetrieval:
    def search(self, query: str, k: int | None = None) -> list[dict]:
        """Hybrid search: dense over-retrieve + BM25 ranks fused via RRF, optional distance gate."""
        k = k or settings.retrieval_k
        q_emb = next(get_embeddings().query_embed(_query_prefix() + query))
        store = get_vector_store()
        if not query.strip():
            return store.query(q_emb, k=k)
        thr = settings.retrieval_distance_threshold
        ranked = hybrid_rank(store, query, q_emb, k, gate=thr, pre_gate_slice=k * 2)[:k]
        if not ranked:
            return []
        hydrated = {h["id"]: h for h in store.fetch([doc_id for doc_id, _, _ in ranked])}
        out = []
        for doc_id, score, dist in ranked:
            h = hydrated.get(doc_id, {"content": "", "metadata": {}})
            out.append(
                {
                    "id": doc_id,
                    "content": h["content"],
                    "metadata": h["metadata"],
                    "score": score,
                    "distance": dist,
                }
            )
        logger.info("retrieval q=%r k=%d fused=%d kept=%d thr=%s", query[:60], k, len(ranked), len(out), thr)
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
