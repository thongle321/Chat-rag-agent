import uuid
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from liteparse import LiteParse
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



TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".xml"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}

_CHEAP_PARSER = LiteParse(output_format="markdown")
_OCR_PARSER = LiteParse(output_format="markdown", ocr_language="vie+eng")


def _load_file(file_path: Path) -> list[Document]:
    suffix = file_path.suffix.lower()

    try:
        if suffix == ".pdf":
            pages = _CHEAP_PARSER.is_complex(file_path)
            parser = _OCR_PARSER if any(p.needs_ocr for p in pages) else _CHEAP_PARSER
            result = parser.parse(file_path)
            text = get_spelling_corrector().fix_spelling(result.text)
            docs = [Document(page_content=text, metadata={})]
        elif suffix in IMAGE_EXTENSIONS:
            result = _OCR_PARSER.parse(file_path)
            text = get_spelling_corrector().fix_spelling(result.text)
            docs = [Document(page_content=text, metadata={})]
        elif suffix in TEXT_EXTENSIONS:
            content = file_path.read_text(encoding="utf-8")
            docs = [Document(page_content=content, metadata={})]
        else:
            return []

        for doc in docs:
            doc.metadata.update(title=file_path.name, source=file_path.name, type=suffix.lstrip("."))
        return docs
    except Exception:
        logger.exception("Failed to load %s", file_path)
        return []

def _index_file(file_path: Path) -> int:
    if not (file_path.is_file() and file_path.suffix.lower() in TEXT_EXTENSIONS | {".pdf"} | IMAGE_EXTENSIONS):
        return 0

    docs = _load_file(file_path)
    if not docs:
        return 0

    chunks = SPLITTER.split_documents(docs)
    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk"] = i
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
