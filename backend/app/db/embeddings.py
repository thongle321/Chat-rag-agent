import logging
from functools import lru_cache

from fastembed import TextEmbedding

from app.core.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_embeddings() -> TextEmbedding:
    logger.info("Loading embedding model: %s", settings.embedding_model)
    return TextEmbedding(
        model_name=settings.embedding_model,
        token=settings.hf_token.get_secret_value() if settings.hf_token else None,
    )
