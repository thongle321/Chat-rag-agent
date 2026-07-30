from functools import lru_cache

from fastembed import TextEmbedding

from app.core.config import settings
import logging


logger = logging.getLogger(__name__)


class FastEmbeddings:
    def __init__(self, model_name: str):
        self._model = TextEmbedding(model_name=model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return list(self._model.embed(texts))

    def embed_query(self, text: str) -> list[float]:
        return next(self._model.query_embed(text))


@lru_cache(maxsize=1)
def get_embeddings() -> FastEmbeddings:
    logger.info("Loading embedding model: %s", settings.embedding_model)
    embeddings = FastEmbeddings(model_name=settings.embedding_model)
    logger.info("Embedding model loaded.")
    return embeddings
