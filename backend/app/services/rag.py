import json
import uuid
from dataclasses import dataclass
from pathlib import Path

import aiosqlite
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

from app.core.config import settings
from app.db.vector_store import embed_model, query_similar
from app.models.schemas import ChatResponse
from app.utils.logger import get_logger

logger = get_logger(__name__)

_checkpoint_db: aiosqlite.Connection | None = None


@dataclass
class ChatDeps:
    context: str


async def get_checkpointer() -> aiosqlite.Connection:
    global _checkpoint_db
    if _checkpoint_db is None:
        ckpt_dir = Path(settings.upload_dir).resolve().parent / "checkpoints"
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        _checkpoint_db = await aiosqlite.connect(str(ckpt_dir / "graph.db"))
        await _checkpoint_db.execute(
            "CREATE TABLE IF NOT EXISTS messages (session_id TEXT PRIMARY KEY, data TEXT)"
        )
        await _checkpoint_db.commit()
        logger.info("SQLite checkpointer initialized at %s", ckpt_dir / "graph.db")
    return _checkpoint_db


async def close_checkpointer():
    global _checkpoint_db
    if _checkpoint_db is not None:
        await _checkpoint_db.close()
        _checkpoint_db = None
        logger.info("Checkpointer closed")


async def get_messages(session_id: str) -> list[dict]:
    """Retrieve messages for a session from the checkpointer state.

    Returns list of {role, content} dicts.
    """
    db = await get_checkpointer()
    cursor = await db.execute("SELECT data FROM messages WHERE session_id = ?", (session_id,))
    row = await cursor.fetchone()
    return json.loads(row[0]) if row else []


async def save_messages(session_id: str, messages: list[dict]):
    """Save conversation history to the checkpointer."""
    db = await get_checkpointer()
    data = json.dumps(messages, ensure_ascii=False, default=str)
    try:
        await db.execute(
            "INSERT OR REPLACE INTO messages (session_id, data) VALUES (?, ?)",
            (session_id, data),
        )
        await db.commit()
    except Exception:
        logger.exception("Failed to save messages to checkpointer")


def _dicts_to_model_messages(messages: list[dict]) -> list[ModelMessage]:
    result = []
    for msg in messages:
        if msg["role"] == "user":
            result.append(ModelRequest(parts=[UserPromptPart(content=msg["content"])]))
        elif msg["role"] == "assistant":
            result.append(ModelResponse(parts=[TextPart(content=msg["content"])]))
    return result


def _model_messages_to_dicts(new_messages: list[ModelMessage]) -> list[dict]:
    result = []
    for msg in new_messages:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, UserPromptPart):
                    result.append({"role": "user", "content": part.content})
        elif isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, TextPart):
                    result.append({"role": "assistant", "content": part.content})
    return result


def _get_model() -> tuple[OllamaModel | OpenAIChatModel, str]:
    provider = settings.ai_provider.lower()
    if provider == "ollama":
        return (
            OllamaModel(
                settings.ollama_model,
                provider=OllamaProvider(
                    base_url=settings.ollama_base_url or "http://localhost:11434",
                    api_key=settings.ollama_api_key or None,
                ),
            ),
            f"ollama/{settings.ollama_model}",
        )
    if provider == "openai":
        return OpenAIChatModel(settings.openai_model), f"openai/{settings.openai_model}"
    raise ValueError("No LLM configured")


def _format_sources(docs: list[dict]) -> list[str]:
    pages_by_title: dict[str, set[int]] = {}
    for d in docs:
        meta = d["metadata"]
        title = meta.get("title", "?")
        page = meta.get("page")
        if title not in pages_by_title:
            pages_by_title[title] = set()
        if page is not None:
            pages_by_title[title].add(page + 1)
    sources = []
    for title, pages in sorted(pages_by_title.items()):
        if pages:
            sources.append(f"{title} (p{', p'.join(str(p) for p in sorted(pages))})")
        else:
            sources.append(title)
    return sources


def _format_context(docs: list[dict]) -> str:
    if not docs:
        return "(No relevant documents found.)"
    parts = []
    for d in docs:
        meta = d["metadata"]
        title = meta.get("title", "unknown")
        page = meta.get("page")
        page_str = f", p.{page + 1}" if page is not None else ""
        parts.append(f"[Source: {title}{page_str}]\n{d['content']}")
    return "\n\n".join(parts)


def _get_agent() -> Agent:
    if _checkpoint_db is None:
        raise RuntimeError("Checkpointer not initialized. Call get_checkpointer() first.")

    system_msg = settings.context_prompt.strip()

    agent = Agent(
        _get_model()[0],
        system_prompt=system_msg,
        deps_type=ChatDeps,
        name="rag_agent",
    )

    @agent.system_prompt
    def _add_context(ctx: RunContext[ChatDeps]) -> str:
        return f"\nRelevant context from the knowledge base:\n\n{ctx.deps.context}"

    return agent


async def answer_question(question: str, session_id: str | None = None) -> ChatResponse:
    _, model_name = _get_model()

    try:
        sid = session_id or str(uuid.uuid4())
        agent = _get_agent()

        history = await get_messages(sid)
        pydantic_history = _dicts_to_model_messages(history)

        query_embedding = embed_model.embed_query(question)
        docs = query_similar(query_embedding, k=5)
        context = _format_context(docs)
        deps = ChatDeps(context=context)

        result = await agent.run(question, deps=deps, message_history=pydantic_history)

        new_dicts = _model_messages_to_dicts(result.new_messages())
        all_messages = history + new_dicts
        await save_messages(sid, all_messages)

        return ChatResponse(
            answer_id=str(uuid.uuid4()),
            answer=result.output or "",
            source_documents=_format_sources(docs),
            model=model_name,
            session_id=sid,
        )
    except Exception:
        # ponytail: broad except intentional for chat UX — all errors become friendly responses
        logger.exception("Chat failed")
        return ChatResponse(
            answer_id=str(uuid.uuid4()),
            answer="Sorry, I could not process your question.",
            source_documents=[],
            model="error",
            session_id=session_id or "",
        )
