import asyncio
import operator
import uuid
from pathlib import Path
from typing import Annotated, Literal

import aiosqlite
from fastapi import HTTPException
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider
from typing_extensions import TypedDict

from app.core.config import settings
from app.db.vector_store import chroma_collection, embed_model, list_documents, query_similar
from app.models.schemas import ChatResponse
import logging


logger = logging.getLogger(__name__)


class RAGState(TypedDict):
    question: str
    messages: Annotated[list[ModelMessage], operator.add]
    source_docs: list[str]
    route: str


class RouteResult(BaseModel):
    category: Literal["chat", "answer"]


# ponytail: two-node graph (route -> chat|answer) — add retrieval re-rank, self-verify nodes when multistep logic lands
_graph = None

_model_instance = None
_model_instance_name = None
_model_key: str | None = None


def _get_model():
    global _model_instance, _model_instance_name, _model_key
    provider = settings.ai_provider.lower()
    model_name = settings.ollama_model if provider == "ollama" else settings.openai_model
    key = f"{provider}:{model_name}"
    if _model_key == key:
        return _model_instance, _model_instance_name
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
    _model_key = key
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


async def _expand_neighbors(docs: list[dict], radius: int = 1) -> list[dict]:
    """Add adjacent chunks (same title, chunk index ± radius) to retrieval results.

    Handles questions whose answer spans a chunk boundary but whose decisive
    chunk scores poorly (e.g. OCR-fragmented text). Requires chunk metadata.
    """
    expanded: dict[tuple[str, int], dict] = {}
    base: set[tuple[str, int]] = set()
    for d in docs:
        m = d["metadata"]
        chunk = m.get("chunk")
        if chunk is None:
            expanded[("", id(d))] = d
            continue
        key = (m.get("title", ""), chunk)
        expanded[key] = d
        base.add(key)
    titles = {m.get("title") for d in docs for m in [d["metadata"]] if m.get("title")}
    if not titles:
        return list(expanded.values())
    result = chroma_collection.get(
        where={"title": {"$in": list(titles)}},
        include=["documents", "metadatas"],
    )
    for doc, meta in zip(result["documents"], result["metadatas"] or []):
        chunk = meta.get("chunk")
        if chunk is None:
            continue
        key = (meta.get("title", ""), chunk)
        if key in expanded:
            continue
        if any(t == key[0] and c - radius <= chunk <= c + radius for (t, c) in base):
            expanded[key] = {"content": doc, "metadata": meta, "score": 0.0}
    return list(expanded.values())


async def answer_node(state: RAGState) -> dict:
    model, _ = _get_model()
    query_embedding = next(embed_model.query_embed(state["question"]))
    docs = query_similar(query_embedding, k=5)
    docs = await _expand_neighbors(docs)
    context = _format_context(docs)
    full_prompt = f"{settings.context_prompt.strip()}\n\nRelevant context from the knowledge base:\n\n{context}"
    agent = Agent(model, system_prompt=full_prompt, name="rag_agent")
    result = await asyncio.wait_for(
        agent.run(state["question"], message_history=state.get("messages", [])),
        timeout=120.0,
    )
    return {"messages": result.new_messages(), "source_docs": _format_sources(docs)}


ROUTER_PROMPT = (
    "You route a user message to a RAG system. "
    "Return 'chat' for greetings, small talk, thanks, or questions about the assistant itself. "
    "Return 'answer' for anything that asks about information contained in documents. "
    "Reply ONLY with the category."
)


async def route_node(state: RAGState) -> dict:
    model, _ = _get_model()
    router = Agent(model, output_type=RouteResult, system_prompt=ROUTER_PROMPT)
    result = await asyncio.wait_for(router.run(state["question"]), timeout=30.0)
    return {"route": result.output.category}


async def chat_node(state: RAGState) -> dict:
    model, _ = _get_model()
    docs = [d for d in list_documents() if d.get("summary")]
    prompt = settings.chat_prompt.strip()
    if docs:
        listing = "\n".join(f"- {d['title']}: {d['summary']}" for d in docs)
        prompt += f"\n\nAvailable documents:\n{listing}"
    agent = Agent(model, system_prompt=prompt, name="chat_agent")
    result = await asyncio.wait_for(
        agent.run(state["question"], message_history=state.get("messages", [])),
        timeout=120.0,
    )
    return {"messages": result.new_messages(), "source_docs": []}


async def get_graph():
    global _graph
    if _graph is not None:
        return _graph
    db_path = Path(settings.upload_dir).resolve().parent / "checkpoints" / "graph.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(str(db_path))
    checkpointer = AsyncSqliteSaver(conn)
    builder = StateGraph(RAGState)
    builder.add_node("route", route_node)
    builder.add_node("chat", chat_node)
    builder.add_node("answer", answer_node)
    builder.add_edge(START, "route")
    builder.add_conditional_edges(
        "route",
        lambda state: state.get("route", "answer"),
        {"chat": "chat", "answer": "answer"},
    )
    builder.add_edge("chat", END)
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
