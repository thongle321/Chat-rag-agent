import os
from functools import lru_cache
from typing import ClassVar

from langchain_huggingface import HuggingFaceEmbeddings

from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PrefixedEmbeddings(HuggingFaceEmbeddings):
    QUERY_INSTRUCTION: ClassVar[str] = "Instruct: Given a question, retrieve passages that can help answer the question.\nQuery: "

    def embed_query(self, text):
        return super().embed_query(f"{self.QUERY_INSTRUCTION}{text}")


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    """Return a cached HuggingFaceEmbeddings instance."""
    logger.info("Loading embedding model: %s", settings.embedding_model)
    if settings.hf_token:
        os.environ["HF_TOKEN"] = settings.hf_token
    embeddings = PrefixedEmbeddings(
        model_name=settings.embedding_model,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True, "batch_size": 32},
    )
    logger.info("Embedding model loaded.")
    return embeddings
