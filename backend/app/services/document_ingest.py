import hashlib
import uuid
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document

from app.core.config import settings
from app.db.vector_store import chroma_collection, embed_model
from app.utils.logger import get_logger

logger = get_logger(__name__)

MARKDOWN_SEPERATORS = [
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
SPLITTER = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=200, add_start_index=True, strip_whitespace=True, separators=MARKDOWN_SEPERATORS, is_separator_regex=True)


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


def _content_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()

EXTENSIONS = {
    ".pdf": PyPDFLoader,
    ".txt": TextLoader,
    ".md": TextLoader,
    ".csv": TextLoader,
    ".json": TextLoader,
    ".xml": TextLoader,
}


def _load_file(file_path: Path) -> list[Document]:
    """Load a single file using the appropriate loader."""
    suffix = file_path.suffix.lower()
    loader_cls = EXTENSIONS.get(suffix)
    if not loader_cls:
        return []

    try:
        loader = loader_cls(str(file_path))
        docs = loader.load()
        for doc in docs:
            doc.page_content = _clean_text(doc.page_content)
            doc.metadata["title"] = file_path.name
        return docs
    except Exception:
        logger.exception("Failed to load %s", file_path)
        return []


def _index_all_sync() -> int:
    """Load all supported files from the upload directory, split, embed, insert."""
    upload_dir = Path(settings.upload_dir)
    if not upload_dir.exists():
        return 0

    all_docs: list[Document] = []
    for file_path in upload_dir.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in EXTENSIONS:
            all_docs.extend(_load_file(file_path))

    if not all_docs:
        return 0

    seen: set[str] = set()
    unique_docs: list[Document] = []
    for doc in all_docs:
        h = _content_hash(doc.page_content)
        if h not in seen:
            seen.add(h)
            unique_docs.append(doc)

    chunks = SPLITTER.split_documents(unique_docs)
    texts = [c.page_content for c in chunks]
    embeddings = embed_model.embed_documents(texts)

    chroma_collection.add(
        ids=[str(uuid.uuid4()) for _ in chunks],
        embeddings=embeddings,
        documents=[c.page_content for c in chunks],
        metadatas=[c.metadata for c in chunks],
    )
    return len(chunks)


async def save_and_queue_indexing(
    filename: str,
    file_bytes: bytes,
) -> tuple[bool, str]:
    """Save file to disk. Returns (saved, message)."""
    upload_folder = Path(settings.upload_dir)
    upload_folder.mkdir(parents=True, exist_ok=True)

    saved_path = upload_folder / filename
    if saved_path.exists():
        return False, f"File '{filename}' already exists."

    saved_path.write_bytes(file_bytes)
    return True, f"File '{filename}' queued for indexing."


def index_all_files_background() -> None:
    """Background task: re-index all files in the upload directory."""
    try:
        chunk_count = _index_all_sync()
        logger.info("Indexed %d chunks from upload directory", chunk_count)
    except Exception:
        logger.exception("Failed to index upload directory")
