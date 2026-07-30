import asyncio
import operator
import uuid
from pathlib import Path
from typing import Annotated

import aiosqlite
from fastapi import HTTPException
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider
from typing_extensions import TypedDict

from app.core.config import settings
from app.db.vector_store import embed_model, query_similar
from app.models.schemas import ChatResponse
import logging


logger = logging.getLogger(__name__)


class RAGState(TypedDict):
    question: str
    messages: Annotated[list[ModelMessage], operator.add]
    source_docs: list[str]


# ponytail: single-node graph — add nodes (retrieval, re-rank, self-verify) when multistep logic lands
_graph = None

# ponytail: cached after first call; restart server after changing AI provider settings
_model_instance = None
_model_instance_name = None


def _get_model():
    global _model_instance, _model_instance_name
    if _model_instance is not None:
        return _model_instance, _model_instance_name
    provider = settings.ai_provider.lower()
    if provider == "ollama":
        _model_instance = OllamaModel(
            settings.ollama_model,
            provider=OllamaProvider(
                base_url=settings.ollama_base_url or "http://localhost:11434",
                api_key=(settings.ollama_api_key.get_secret_value() if hasattr(settings.ollama_api_key, 'get_secret_value') else settings.ollama_api_key) or None,
            ),
        )
        _model_instance_name = f"ollama/{settings.ollama_model}"
    elif provider == "openai":
        _model_instance = OpenAIChatModel(settings.openai_model)
        _model_instance_name = f"openai/{settings.openai_model}"
    else:
        raise ValueError("No LLM configured")
    return _model_instance, _model_instance_name


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


def _last_output(messages: list[ModelMessage]) -> str:
    return next((p.content for m in reversed(messages) if isinstance(m, ModelResponse) for p in m.parts if isinstance(p, TextPart)), "")


async def get_messages(session_id: str) -> list[dict]:
    g = await get_graph()
    snap = await g.aget_state({"configurable": {"thread_id": session_id}})
    msgs = snap.values.get("messages", [])
    result = []
    for m in msgs:
        if isinstance(m, ModelRequest):
            for p in m.parts:
                if isinstance(p, UserPromptPart):
                    result.append({"role": "user", "content": p.content})
        elif isinstance(m, ModelResponse):
            for p in m.parts:
                if isinstance(p, TextPart):
                    result.append({"role": "assistant", "content": p.content})
    return result


async def answer_node(state: RAGState) -> dict:
    model, _ = _get_model()
    query_embedding = embed_model.embed_query(state["question"])
    docs = query_similar(query_embedding, k=5)
    context = _format_context(docs)
    full_prompt = f"{settings.context_prompt.strip()}\n\nRelevant context from the knowledge base:\n\n{context}"
    agent = Agent(model, system_prompt=full_prompt, name="rag_agent")
    result = await asyncio.wait_for(
        agent.run(state["question"], message_history=state.get("messages", [])),
        timeout=120.0,
    )
    return {"messages": result.new_messages(), "source_docs": _format_sources(docs)}


async def get_graph():
    global _graph
    if _graph is not None:
        return _graph
    db_path = Path(settings.upload_dir).resolve().parent / "checkpoints" / "graph.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(str(db_path))
    checkpointer = AsyncSqliteSaver(conn)
    builder = StateGraph(RAGState)
    builder.add_node("answer", answer_node)
    builder.add_edge(START, "answer")
    builder.add_edge("answer", END)
    _graph = builder.compile(checkpointer=checkpointer)
    logger.info("Graph compiled with SQLite checkpointer at %s", db_path)
    return _graph


async def answer_question(question: str, session_id: str | None = None) -> ChatResponse:
    _, model_name = _get_model()
    try:
        sid = session_id or str(uuid.uuid4())
        g = await get_graph()
        state = await g.ainvoke(
            {"question": question},
            {"configurable": {"thread_id": sid}},
        )
        return ChatResponse(
            answer_id=str(uuid.uuid4()),
            answer=_last_output(state.get("messages", [])),
            source_documents=state.get("source_docs", []),
            model=model_name,
            session_id=sid,
        )
    except Exception:
        logger.exception("Chat failed for session %s", session_id)
        raise HTTPException(status_code=500, detail="I encountered an error while processing your request. Please try again.")
