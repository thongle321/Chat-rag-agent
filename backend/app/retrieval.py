import logging
from functools import lru_cache

import bm25s

from app.core.config import settings
from app.db.embeddings import get_embeddings
from app.db.embeddings import passage_prefix as _passage_prefix
from app.db.embeddings import query_prefix as _query_prefix
from app.db.vector_store import _STOPWORDS, get_vector_store
from app.db.vector_store import rrf as _rrf

logger = logging.getLogger(__name__)


class ChromaRetrieval:
    def search(self, query: str, k: int | None = None) -> list[dict]:
        k = k or settings.retrieval_k
        if not query.strip():
            q_emb = next(get_embeddings().query_embed(_query_prefix() + query))
            return get_vector_store().query(q_emb, k=k)
        q_emb = next(get_embeddings().query_embed(_query_prefix() + query))
        store = get_vector_store()
        # over-retrieve for gate
        over = settings.retrieval_bm25_overretrieve
        vec_hits = store.query(q_emb, k=k * over)
        # keep distances for gate
        dist_by_id = {h["id"]: h["score"] for h in vec_hits}
        vec_ranks = [h["id"] for h in vec_hits]
        # bm25 ranks
        bm25_ids = store._ensure_bm25()
        if not bm25_ids:
            fused = [(h["id"], 1.0 / (settings.retrieval_rrf_k + i + 1)) for i, h in enumerate(vec_hits)]
            fused = fused[: k * 2]
        else:
            hits, _ = store._bm25.retrieve(
                bm25s.tokenize(query, stopwords=_STOPWORDS, show_progress=False),
                k=k * over,
                show_progress=False,
            )
            bm25_ranks = [bm25_ids[i] for i in hits[0]]
            fused = _rrf([vec_ranks, bm25_ranks], k=settings.retrieval_rrf_k)[: k * 2]
        # gate on cosine distance if enabled
        if settings.retrieval_distance_threshold is not None:
            gated = [(doc_id, sc) for doc_id, sc in fused if dist_by_id.get(doc_id, 2.0) < settings.retrieval_distance_threshold]
            fused = gated[:k] if gated else []
        else:
            fused = fused[:k]
        if not fused:
            return []
        res = store._collection.get(ids=[i for i, _ in fused], include=["documents", "metadatas"])
        doc_by_id = dict(zip(res["ids"], res["documents"], strict=True))
        meta_by_id = dict(zip(res["ids"], res["metadatas"], strict=True))
        out = []
        for doc_id, score in fused:
            out.append(
                {
                    "id": doc_id,
                    "content": doc_by_id.get(doc_id, ""),
                    "metadata": meta_by_id.get(doc_id, {}),
                    "score": score,
                    "distance": dist_by_id.get(doc_id),
                }
            )
        logger.info("retrieval q=%r k=%d fused=%d kept=%d thr=%s", query[:60], k, len(fused), len(out), settings.retrieval_distance_threshold)
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
