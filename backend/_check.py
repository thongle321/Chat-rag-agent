from pathlib import Path
from langchain_community.document_loaders import DirectoryLoader
from langchain_unstructured import UnstructuredLoader

upload_dir = "D:/chat-rag-agent/backend/data/uploads"

# Check files first
p = Path(upload_dir)
print("Files in upload dir:")
for f in p.iterdir():
    print(f"  {f.name} (suffix={f.suffix})")

# Try with simple glob
loader = DirectoryLoader(
    upload_dir,
    glob="*.pdf",
    loader_cls=UnstructuredLoader,
    show_progress=False,
    silent_errors=True,
)
docs = loader.load()
print(f"Loaded {len(docs)} docs with glob='*.pdf'")

# Try without glob
loader2 = DirectoryLoader(
    upload_dir,
    loader_cls=UnstructuredLoader,
    show_progress=False,
    silent_errors=True,
)
docs2 = loader2.load()
print(f"Loaded {len(docs2)} docs without glob")
