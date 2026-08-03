# Document RAG Chatbot

This project is a starter template for a document-based retrieval-augmented chatbot using Python + FastAPI for the backend and Vue 3 for the frontend.

Features:
- Ingest Documents metadata and text content
- Upload plain documents for indexing
- Query ingested documents with a chat endpoint
- Placeholder integration hooks for ZaloOA and Facebook Fanpage

## Structure

- `backend/` - FastAPI backend
- `frontend/` - Vue 3 frontend

## Running the backend

1. Create a virtual environment
2. Install dependencies: `uv sync` (or `pip install -e .`)
3. Run `fastapi dev` for development (auto-reload) or `fastapi run` for production

## Running the frontend

1. In `frontend`, install dependencies with `pnpm install`
2. Start dev server with `pnpm dev`
