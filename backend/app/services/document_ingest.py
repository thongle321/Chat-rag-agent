import hashlib
import json
import uuid
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader
from langchain_pymupdf4llm import PyMuPDF4LLMLoader
from langchain_core.documents import Document

from app.core.config import settings
from app.db.vector_store import chroma_collection, embed_model
from app.utils.logger import get_logger

logger = get_logger(__name__)

MANIFEST_PATH = Path(settings.vector_store_dir) / "_manifest.json"

BATCH_SIZE = 500

MARKDOWN_SEPARATORS = [
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


EXTENSIONS = {
    ".pdf": PyMuPDF4LLMLoader,
    ".txt": TextLoader,
    ".md": TextLoader,
    ".csv": TextLoader,
    ".json": TextLoader,
    ".xml": TextLoader,
}


def _load_file(file_path: Path) -> list[Document]:
    """Load a single file using the appropriate loader."""
    suffix = file_path.suffix.lower()

    try:
        if suffix == ".pdf":
            loader = PyMuPDF4LLMLoader(str(file_path), mode="single")
            docs = loader.load()
        else:
            loader_cls = EXTENSIONS.get(suffix)
            if not loader_cls:
                return []
            loader = loader_cls(str(file_path))
            docs = loader.load()
        for doc in docs:
            doc.page_content = _clean_text(doc.page_content)
            doc.metadata["title"] = file_path.name
        return docs
    except Exception:
        logger.exception("Failed to load %s", file_path)
        return []


def _load_manifest() -> dict[str, str]:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {}


def _save_manifest(manifest: dict[str, str]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _file_hash(file_path: Path) -> str:
    return hashlib.md5(file_path.read_bytes()).hexdigest()


def _index_file(file_path: Path) -> int:
    """Index a single file. Returns chunk count added."""
    if not (file_path.is_file() and file_path.suffix.lower() in EXTENSIONS):
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

    # Update manifest for this file
    manifest = _load_manifest()
    manifest[file_path.name] = _file_hash(file_path)
    _save_manifest(manifest)

    logger.info("Indexed %d chunks from %s", len(chunks), file_path.name)
    return len(chunks)


async def save_and_queue_indexing(
    filename: str,
    file_bytes: bytes,
) -> tuple[bool, str, Path | None]:
    """Save file to disk. Returns (saved, message, saved_path)."""
    upload_folder = Path(settings.upload_dir)
    upload_folder.mkdir(parents=True, exist_ok=True)

    saved_path = upload_folder / filename
    if saved_path.exists():
        return False, f"File '{filename}' already exists.", None

    saved_path.write_bytes(file_bytes)
    return True, f"File '{filename}' queued for indexing.", saved_path
