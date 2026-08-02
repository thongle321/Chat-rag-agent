import asyncio
import uuid
from pathlib import Path

from chonkie import RecursiveChunker
from liteparse import LiteParse
from pydantic_ai import Agent

from app.core.config import settings
from app.db.vector_store import chroma_collection, embed_model, delete_document
from app.services.rag import _get_model
from app.services.spelling_correction import get_spelling_corrector
import logging


logger = logging.getLogger(__name__)

BATCH_SIZE = 500

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".xml"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}

_CHEAP_PARSER = LiteParse(output_format="markdown")
_OCR_PARSER = LiteParse(output_format="markdown", ocr_language="vie+eng")

chunker = RecursiveChunker(
    tokenizer="character",
    chunk_size=1200,
    min_characters_per_chunk=24,
)


SUMMARY_PROMPT = (
    "Summarize the following document excerpt in 1-2 sentences, "
    "describing the main topics it covers. Reply ONLY with the summary."
)


async def _summarize(text: str) -> str:
    try:
        model, _ = _get_model()
        agent = Agent(model, system_prompt=SUMMARY_PROMPT)
        result = await asyncio.wait_for(agent.run(text[:3000]), timeout=60.0)
        return result.output.strip()[:500]
    except Exception:
        logger.exception("Summary generation failed")
        return ""


async def _load_file(file_path: Path) -> tuple[str, dict] | None:
    suffix = file_path.suffix.lower()

    try:
        if suffix == ".pdf":
            pages = _CHEAP_PARSER.is_complex(file_path)
            parser = _OCR_PARSER if any(p.needs_ocr for p in pages) else _CHEAP_PARSER
            result = parser.parse(file_path)
            text = get_spelling_corrector().fix_spelling(result.text)
        elif suffix in IMAGE_EXTENSIONS:
            result = _OCR_PARSER.parse(file_path)
            text = get_spelling_corrector().fix_spelling(result.text)
        elif suffix in TEXT_EXTENSIONS:
            text = file_path.read_text(encoding="utf-8")
        else:
            return None

        summary = await _summarize(text)
        base_metadata = {
            "title": file_path.name,
            "source": file_path.name,
            "type": suffix.lstrip("."),
            "summary": summary,
        }
        return text, base_metadata
    except Exception:
        logger.exception("Failed to load %s", file_path)
        return None

async def _index_file(file_path: Path) -> int:
    if not (file_path.is_file() and file_path.suffix.lower() in TEXT_EXTENSIONS | {".pdf"} | IMAGE_EXTENSIONS):
        return 0

    result = await _load_file(file_path)
    if result is None:
        return 0

    text, base_metadata = result
    chunks = chunker.chunk(text)
    if not chunks:
        return 0

    chunk_texts = []
    chunk_metadatas = []
    for i, chunk in enumerate(chunks):
        chunk_texts.append(chunk.text)
        chunk_metadatas.append({**base_metadata, "chunk": i})

    embeddings_list = list(embed_model.embed(chunk_texts))

    for i in range(0, len(chunks), BATCH_SIZE):
        batch_texts = chunk_texts[i : i + BATCH_SIZE]
        batch_embeddings = embeddings_list[i : i + BATCH_SIZE]
        batch_metadatas = chunk_metadatas[i : i + BATCH_SIZE]
        chroma_collection.add(
            ids=[str(uuid.uuid4()) for _ in batch_texts],
            embeddings=batch_embeddings,
            documents=batch_texts,
            metadatas=batch_metadatas,
        )

    logger.info("Indexed %d chunks from %s", len(chunks), file_path.name)
    return len(chunks)

async def save_and_queue_indexing(
    filename: str,
    file_bytes: bytes,
) -> tuple[str, Path]:
    upload_folder = Path(settings.upload_dir)
    upload_folder.mkdir(parents=True, exist_ok=True)

    saved_path = upload_folder / filename
    if saved_path.exists():
        saved_path.unlink()
        delete_document(filename)

    saved_path.write_bytes(file_bytes)
    return f"File '{filename}' queued for indexing.", saved_path
