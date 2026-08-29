import asyncio
import logging
import uuid
from pathlib import Path

from chonkie import RecursiveChunker
from liteparse import LiteParse
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from app.core.config import settings
from app.models.document_status import COMPLETED, FAILED, PENDING, PROCESSING
from app.retrieval import get_retrieval
from app.services.document_status import set_document_status
from app.services.llm import get_llm

logger = logging.getLogger(__name__)

BATCH_SIZE = 500

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".xml"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}

_CHEAP_PARSER = LiteParse(output_format="markdown")
# dpi=400: default render DPI dropped digits in scanned legal docs (e.g. "3.000 tỷ đồng" in Điều 7)
_OCR_PARSER = LiteParse(output_format="markdown", ocr_language="vie+eng", dpi=400)

chunker = RecursiveChunker(
    tokenizer="character",
    chunk_size=1200,
    min_characters_per_chunk=24,
)


SUMMARY_PROMPT = (
    "Return exactly two lines:\n"
    "Title: <short natural title>\n"
    "Reference: <optional: document reference number, year, or code, if present.>"
)

_SUMMARY_LIMITS = UsageLimits(request_limit=3)


async def _summarize(text: str) -> tuple[str, str]:
    try:
        model, _ = get_llm()
        agent = Agent(model, system_prompt=SUMMARY_PROMPT)
        result = await asyncio.wait_for(agent.run(text[:3000], usage_limits=_SUMMARY_LIMITS), timeout=60.0)
        title = ""
        reference = ""
        for line in result.output.strip().splitlines():
            line = line.strip()
            if line.startswith("Title:"):
                title = line[len("Title:") :].strip()
            elif line.startswith("Reference:"):
                reference = line[len("Reference:") :].strip()
        return title, reference
    except Exception:
        logger.exception("Title generation failed")
        return "", ""


async def _load_file(file_path: Path) -> tuple[str, dict] | None:
    suffix = file_path.suffix.lower()

    try:
        if suffix == ".pdf":
            pages = await asyncio.to_thread(_CHEAP_PARSER.is_complex, file_path)
            parser = _OCR_PARSER if any(p.needs_ocr for p in pages) else _CHEAP_PARSER
            result = await asyncio.to_thread(parser.parse, file_path)
            text = result.text
        elif suffix in IMAGE_EXTENSIONS:
            result = await asyncio.to_thread(_OCR_PARSER.parse, file_path)
            text = result.text
        elif suffix in TEXT_EXTENSIONS:
            text = file_path.read_text(encoding="utf-8")
        else:
            return None

        title, reference = await _summarize(text)

        base_metadata = {
            "title": file_path.name,
            "clean_title": title or file_path.name,
            "source": file_path.name,
            "type": suffix.lstrip("."),
            "reference": reference,
        }
        return text, base_metadata
    except Exception:
        logger.exception("Failed to load %s", file_path)
        return None


async def index_file(file_path: Path) -> int:
    if not (file_path.is_file() and file_path.suffix.lower() in TEXT_EXTENSIONS | {".pdf"} | IMAGE_EXTENSIONS):
        await set_document_status(file_path.name, status=FAILED, error_message="Unsupported file type.")
        return 0

    await set_document_status(file_path.name, status=PROCESSING)

    try:
        result = await _load_file(file_path)
        if result is None:
            await set_document_status(file_path.name, status=FAILED, error_message="Failed to parse the file.")
            return 0

        text, base_metadata = result
        chunks = chunker.chunk(text)
        if not chunks:
            await set_document_status(file_path.name, status=FAILED, error_message="No text chunks could be generated.")
            return 0

        chunk_texts = []
        chunk_metadatas = []
        for i, chunk in enumerate(chunks):
            chunk_texts.append(chunk.text)
            chunk_metadatas.append({**base_metadata, "chunk": i})

        embeddings_list = await asyncio.to_thread(get_retrieval().ingest_embed, chunk_texts)

        store = get_retrieval()
        for i in range(0, len(chunks), BATCH_SIZE):
            batch_texts = chunk_texts[i : i + BATCH_SIZE]
            batch_embeddings = embeddings_list[i : i + BATCH_SIZE]
            batch_metadatas = chunk_metadatas[i : i + BATCH_SIZE]
            await asyncio.to_thread(
                store.add,
                ids=[str(uuid.uuid4()) for _ in batch_texts],
                embeddings=batch_embeddings,
                documents=batch_texts,
                metadatas=batch_metadatas,
            )

        await set_document_status(file_path.name, status=COMPLETED, chunk_count=len(chunks))
        logger.info("Indexed %d chunks from %s", len(chunks), file_path.name)
        return len(chunks)
    except Exception:
        await set_document_status(file_path.name, status=FAILED, error_message="Indexing failed unexpectedly.")
        logger.exception("Indexing failed for %s", file_path.name)
        return 0


async def save_and_queue_indexing(
    filename: str,
    file_bytes: bytes,
) -> tuple[str, Path]:
    upload_folder = Path(settings.upload_dir)
    upload_folder.mkdir(parents=True, exist_ok=True)

    saved_path = upload_folder / filename
    if saved_path.exists():
        saved_path.unlink()
        await asyncio.to_thread(get_retrieval().delete_document, filename)

    saved_path.write_bytes(file_bytes)
    await set_document_status(filename, status=PENDING)
    # ponytail: no auto-retry of pending rows on restart — same limit as background task instead of a queue
    return f"File '{filename}' queued for indexing.", saved_path
