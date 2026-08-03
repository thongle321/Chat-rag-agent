import logging
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


@lru_cache(maxsize=1)
def get_embeddings() -> TextEmbedding:
    if settings.embedding_model in _CUSTOM_MODELS:
        TextEmbedding.add_custom_model(
            settings.embedding_model, **_CUSTOM_MODELS[settings.embedding_model]
        )
    logger.info("Loading embedding model: %s", settings.embedding_model)
    return TextEmbedding(
        model_name=settings.embedding_model,
        token=settings.hf_token.get_secret_value() if settings.hf_token else None,
    )


def _check() -> None:
    q = list(get_embeddings().query_embed(query_prefix() + "Nghị định 135 có hiệu lực"))
    p = list(get_embeddings().embed([passage_prefix() + "Nghị định này có hiệu lực thi hành"]))
    assert q[0].shape == p[0].shape == (384,), f"unexpected dim: {q[0].shape} vs {p[0].shape}"
    print("embeddings check OK")


if __name__ == "__main__":
    _check()
