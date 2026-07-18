from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings

from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PrefixedEmbeddings(HuggingFaceEmbeddings):
    def embed_documents(self, texts):
        if "e5" in settings.embedding_model:
            texts = [f"passage: {t}" for t in texts]
        return super().embed_documents(texts)

    def embed_query(self, text):
        if "e5" in settings.embedding_model:
            return super().embed_query(f"query: {text}")
        return super().embed_query(text)


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    """Return a cached HuggingFaceEmbeddings instance."""
    logger.info("Loading embedding model: %s", settings.embedding_model)
    embeddings = PrefixedEmbeddings(
        model_name=settings.embedding_model,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True, "batch_size": 32},
    )
    logger.info("Embedding model loaded.")
    return embeddings
