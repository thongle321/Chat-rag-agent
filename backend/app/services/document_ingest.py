import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import fitz
from langchain_pymupdf4llm import PyMuPDF4LLMLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from rapidocr_onnxruntime import RapidOCR

from app.core.config import settings
from app.db.vector_store import chroma_collection, embed_model, delete_document
from app.services.spelling_correction import get_spelling_corrector
from app.utils.logger import get_logger

logger = get_logger(__name__)

BATCH_SIZE = 500

MARKDOWN_SEPARATORS = [
    "(?<=[.?!;:])\\s+",
    "\n#{1,6} ",
    "```\n",
    "\n\\*\\*\\*+\n",
    "\n---+\n",
    "\n___+\n",
    "\n\n",
    "\n",
    " ",
    "",
]
SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=1200,
    chunk_overlap=200,
    add_start_index=True,
    strip_whitespace=True,
    separators=MARKDOWN_SEPARATORS,
    is_separator_regex=True,
)


def _clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned, blank_run = [], 0
    for line in lines:
        if line == "":
            blank_run += 1
            if blank_run <= 2:
                cleaned.append(line)
        else:
            blank_run = 0
            cleaned.append(line)
    return "\n".join(cleaned).strip()


_OCR_ENGINE = None


def _get_ocr_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        logger.info("Loading RapidOCR engine...")
        _OCR_ENGINE = RapidOCR()
        logger.info("RapidOCR engine loaded")
    return _OCR_ENGINE


def _ocr_pdf(file_path: Path) -> list[Document]:
    engine = _get_ocr_engine()
    corrector = get_spelling_corrector()
    doc = fitz.open(str(file_path))

    def _ocr_page(page_num: int) -> str:
        page = doc[page_num]
        pix = page.get_pixmap(dpi=200)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            img = img[:, :, :3]
        result, _ = engine(img)
        if result is None:
            return ""
        page_text = "\n".join(text for _, text, _ in result)
        return corrector.fix_spelling(page_text)

    with ThreadPoolExecutor(max_workers=4) as pool:
        texts = list(pool.map(_ocr_page, range(len(doc))))

    doc.close()
    full_text = _clean_text("\n\n".join(texts))
    return [Document(page_content=full_text, metadata={"title": file_path.name, "ocr": True})]


TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".xml"}


def _load_file(file_path: Path) -> list[Document]:
    suffix = file_path.suffix.lower()

    try:
        if suffix == ".pdf":
            loader = PyMuPDF4LLMLoader(str(file_path), mode="single")
            docs = loader.load()
            text_len = sum(len(d.page_content) for d in docs)
            with fitz.open(str(file_path)) as pdf:
                page_count = len(pdf)
            if text_len < max(100, page_count * 80):
                logger.info("PDF appears to be scanned (text=%d for %d pages), falling back to OCR: %s", text_len, page_count, file_path.name)
                docs = _ocr_pdf(file_path)
        elif suffix in TEXT_EXTENSIONS:
            content = file_path.read_text(encoding="utf-8")
            docs = [Document(page_content=content, metadata={})]
        else:
            return []

        for doc in docs:
            doc.page_content = _clean_text(doc.page_content)
            doc.metadata["title"] = file_path.name
        return docs
    except Exception:
        logger.exception("Failed to load %s", file_path)
        return []


def _index_file(file_path: Path) -> int:
    if not (file_path.is_file() and file_path.suffix.lower() in TEXT_EXTENSIONS | {".pdf"}):
        return 0

    docs = _load_file(file_path)
    if not docs:
        return 0

    chunks = SPLITTER.split_documents(docs)
    texts = [c.page_content for c in chunks]
    embeddings_list = embed_model.embed_documents(texts)

    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        batch_embeddings = embeddings_list[i : i + BATCH_SIZE]
        chroma_collection.add(
            ids=[str(uuid.uuid4()) for _ in batch],
            embeddings=batch_embeddings,
            documents=[c.page_content for c in batch],
            metadatas=[c.metadata for c in batch],
        )

    logger.info("Indexed %d chunks from %s", len(chunks), file_path.name)
    return len(chunks)


async def save_and_queue_indexing(
    filename: str,
    file_bytes: bytes,
) -> tuple[bool, str, Path | None]:
    upload_folder = Path(settings.upload_dir)
    upload_folder.mkdir(parents=True, exist_ok=True)

    saved_path = upload_folder / filename
    if saved_path.exists():
        saved_path.unlink()
        delete_document(filename)

    saved_path.write_bytes(file_bytes)
    return True, f"File '{filename}' queued for indexing.", saved_path
