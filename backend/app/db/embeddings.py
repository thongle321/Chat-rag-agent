import logging
import math
import os
from functools import lru_cache

from fastembed import TextEmbedding
from fastembed.common.model_description import ModelSource, PoolingType

from app.core.config import settings

logger = logging.getLogger(__name__)

# Custom models not in fastembed's built-in registry. Add entries to register any
# model whose HF repo ships an ONNX export (onnx/model.onnx).
_CUSTOM_MODELS: dict[str, dict] = {
    "intfloat/multilingual-e5-small": {
        "pooling": PoolingType.CLS,
        "normalization": True,
        "sources": ModelSource(hf="intfloat/multilingual-e5-small"),
        "dim": 384,
        "model_file": "onnx/model.onnx",
    },
}


def query_prefix() -> str:
    """e5-family models are trained with a 'query: ' prefix — prepend at query time only."""
    return "query: " if "e5" in settings.embedding_model.lower() else ""


def passage_prefix() -> str:
    """e5-family models are trained with a 'passage: ' prefix — prepend at ingest time only."""
    return "passage: " if "e5" in settings.embedding_model.lower() else ""


def cosine_sim(a: list[float], b: list[float]) -> float:
    """Cosine similarity for same-length embedding vectors (0.0 on mismatch)."""
    if len(a) != len(b):
        return 0.0
    denom = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    if not denom:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True)) / denom


@lru_cache(maxsize=1)
def get_embeddings() -> TextEmbedding:
    if settings.embedding_model in _CUSTOM_MODELS:
        TextEmbedding.add_custom_model(
            settings.embedding_model, **_CUSTOM_MODELS[settings.embedding_model]
        )
    hf = settings.hf_token.get_secret_value() if settings.hf_token else None
    if hf:
        os.environ.setdefault("HF_TOKEN", hf)
    logger.info("HF token configured: %s", bool(hf))
    logger.info("Loading embedding model: %s", settings.embedding_model)
    return TextEmbedding(
        model_name=settings.embedding_model,
        token=hf,
    )
