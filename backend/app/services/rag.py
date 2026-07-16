import re
import uuid
from pathlib import Path

import aiosqlite
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.utils.uuid import uuid7
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.core.config import settings
from app.db.vector_store import vector_store
from app.models.schemas import ChatResponse
from app.utils.logger import get_logger

logger = get_logger(__name__)

_checkpointer: AsyncSqliteSaver | None = None
_cached_agent = None
_cached_agent_key: str = ""

_CONTEXT_PREFIX = "Context:\n"

def _strip_injected_context(content: str) -> str:
    if content.startswith(_CONTEXT_PREFIX):
        m = re.search(r"\n\nQuestion: ", content)
        if m:
            return content[m.end():]
    return content


async def get_checkpointer() -> AsyncSqliteSaver:
    global _checkpointer
    if _checkpointer is None:
        ckpt_dir = Path(settings.upload_dir).resolve().parent / "checkpoints"
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(str(ckpt_dir / "graph.db"))
        _checkpointer = AsyncSqliteSaver(conn)
        await _checkpointer.setup()
        logger.info("AsyncSqliteSaver initialized at %s", ckpt_dir / "graph.db")
    return _checkpointer


async def close_checkpointer():
    global _checkpointer
    if _checkpointer is not None:
        await _checkpointer.conn.close()
        _checkpointer = None
        logger.info("Checkpointer closed")


async def get_messages(session_id: str) -> list[dict]:
    """Retrieve messages for a session from the checkpointer state.

    Returns list of {role, content} dicts.
    """
    cp = await get_checkpointer()
    config = {"configurable": {"thread_id": session_id}}
    checkpoint = await cp.aget(config)
    if not checkpoint:
        return []
    raw_messages = checkpoint["channel_values"].get("messages", [])
    out = []
    for m in raw_messages:
        if hasattr(m, "type") and m.type in ("human", "ai"):
            out.append({
                "role": "user" if m.type == "human" else "assistant",
                "content": _strip_injected_context(m.content or ""),
            })
    return out


def _get_model() -> BaseChatModel:
    provider = settings.ai_provider.lower()
    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=settings.ollama_model, base_url=settings.ollama_base_url)
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=settings.openai_model)
    raise ValueError("No LLM configured")


def _model_display() -> str:
    provider = settings.ai_provider.lower()
    if provider == "ollama":
        return f"ollama/{settings.ollama_model}"
    if provider == "openai":
        return f"openai/{settings.openai_model}"
    return "none"


def _format_sources(docs: list) -> list[str]:
    pages_by_title: dict[str, set[int]] = {}
    for d in docs:
        title = d.metadata.get("title", "?")
        page = d.metadata.get("page")
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


def _format_context(docs: list) -> str:
    if not docs:
        return "(No relevant documents found.)"
    parts = []
    for d in docs:
        title = d.metadata.get("title", "unknown")
        page = d.metadata.get("page")
        page_str = f", page {page + 1}" if page is not None else ""
        parts.append(f"[Source: {title}{page_str}]\n{d.page_content}")
    return "\n\n".join(parts)


def _get_agent():
    global _cached_agent, _cached_agent_key

    if _checkpointer is None:
        raise RuntimeError("Checkpointer not initialized. Call get_checkpointer() first.")

    system_msg = settings.context_prompt.strip()
    key = f"{settings.ai_provider}:{settings.ollama_model}:{settings.openai_model}:{system_msg}"

    if _cached_agent is not None and _cached_agent_key == key:
        return _cached_agent

    agent = create_agent(
        model=_get_model(),
        tools=[],
        system_prompt=system_msg,
        checkpointer=_checkpointer,
    )

    _cached_agent = agent
    _cached_agent_key = key
    logger.info("Created new agent for config: %s", key)
    return agent


async def answer_question(question: str, session_id: str | None = None) -> ChatResponse:
    model_name = _model_display()

    try:
        sid = session_id or str(uuid7())
        agent = _get_agent()

        retriever = vector_store.as_retriever(
            search_type="mmr",
            search_kwargs={"k": 10, "fetch_k": 20},
        )
        docs = retriever.invoke(question)
        context = _format_context(docs)

        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}]},
            {"configurable": {"thread_id": sid}},
        )

        answer = ""
        for msg in reversed(result["messages"]):
            if hasattr(msg, "content") and msg.content and msg.type == "ai":
                answer = msg.content
                break

        return ChatResponse(
            answer_id=str(uuid.uuid4()),
            answer=answer,
            source_documents=_format_sources(docs),
            model=model_name,
            session_id=sid,
        )
    except Exception:
        logger.exception("Chat failed")
        return ChatResponse(
            answer_id=str(uuid.uuid4()),
            answer="Sorry, I could not process your question.",
            source_documents=[],
            model="error",
            session_id=session_id or "",
        )
