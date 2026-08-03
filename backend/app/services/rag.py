import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.capabilities import ReinjectSystemPrompt
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_graph import BaseNode, End, GraphBuilder, GraphRunContext, StepContext

from app.core.config import settings
from app.db.conversation_store import load_messages, save_messages
from app.db.embeddings import get_embeddings
from app.db.vector_store import get_vector_store
from app.models.schemas import ChatResponse
from app.services.llm import get_llm

logger = logging.getLogger(__name__)


class RouteResult(BaseModel):
    category: Literal["chat", "answer"]


@dataclass
class RAGState:
    question: str
    history: list[ModelMessage] = field(default_factory=list)
    new_messages: list[ModelMessage] = field(default_factory=list)
    source_docs: list[str] = field(default_factory=list)


# ponytail: three-node graph (route -> chat|answer) — add re-rank, self-verify nodes when multistep logic lands
_graph = None


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
    return next(
        (
            p.content
            for m in reversed(messages)
            if isinstance(m, ModelResponse)
            for p in m.parts
            if isinstance(p, TextPart)
        ),
        "",
    )


async def get_messages(session_id: str) -> list[dict]:
    result = []
    for m in await load_messages(session_id):
        if isinstance(m, ModelRequest):
            for p in m.parts:
                if isinstance(p, UserPromptPart):
                    result.append({"role": "user", "content": p.content})
        elif isinstance(m, ModelResponse):
            for p in m.parts:
                if isinstance(p, TextPart):
                    result.append({"role": "assistant", "content": p.content})
    return result


REWRITE_PROMPT = (
    "Given the conversation history and the latest user message, "
    "rewrite the latest message into a single standalone question that "
    "contains all the context needed to answer it on its own. "
    "Replace pronouns and vague references with specific nouns. "
    "Fill in any missing subject or object. "
    "Keep entity names, product codes, and acronyms verbatim. "
    "If the message is already standalone, return it unchanged. "
    "If the message is chit-chat with no question, return it unchanged. "
    "Never add facts that were not in the conversation. "
    "Reply ONLY with the rewritten question, nothing else."
)

_MAX_HISTORY = 10


async def _rewrite_question(question: str, messages: list[ModelMessage]) -> str:
    if not messages:
        return question
    model, _ = get_llm()
    agent = Agent(
        model,
        system_prompt=REWRITE_PROMPT,
        capabilities=[ReinjectSystemPrompt(replace_existing=True)],
    )
    result = await asyncio.wait_for(
        agent.run(question, message_history=messages[-_MAX_HISTORY:]),
        timeout=30.0,
    )
    first_line = str(result.output or "").strip().split("\n", 1)[0].strip()
    return (first_line[:400] or question) if first_line else question


ROUTER_PROMPT = (
    "You route a user message to a RAG system. "
    "Return 'chat' for greetings, small talk, thanks, or questions about the assistant itself. "
    "Return 'answer' for anything that asks about information contained in documents. "
    "Reply ONLY with the category."
)


@dataclass
class Route(BaseNode[RAGState]):
    async def run(self, ctx: GraphRunContext[RAGState]) -> "Chat | Answer":
        model, _ = get_llm()
        router = Agent(
            model,
            output_type=RouteResult,
            system_prompt=ROUTER_PROMPT,
            capabilities=[ReinjectSystemPrompt(replace_existing=True)],
        )
        result = await asyncio.wait_for(
            router.run(ctx.state.question, message_history=ctx.state.history[-_MAX_HISTORY:]),
            timeout=30.0,
        )
        return Chat() if result.output.category == "chat" else Answer()


@dataclass
class Chat(BaseNode[RAGState, None, None]):
    async def run(self, ctx: GraphRunContext[RAGState]) -> End[None]:
        model, _ = get_llm()
        docs = [d for d in get_vector_store().list_documents() if d.get("summary")]
        prompt = settings.chat_prompt.strip()
        if docs:
            listing = "\n".join(f"- {d['title']}: {d['summary']}" for d in docs)
            prompt += f"\n\nAvailable documents:\n{listing}"
        agent = Agent(
            model,
            system_prompt=prompt,
            name="chat_agent",
            capabilities=[ReinjectSystemPrompt(replace_existing=True)],
        )
        result = await asyncio.wait_for(
            agent.run(ctx.state.question, message_history=ctx.state.history),
            timeout=120.0,
        )
        ctx.state.new_messages = result.new_messages()
        ctx.state.source_docs = []
        return End(None)


@dataclass
class Answer(BaseNode[RAGState, None, None]):
    async def run(self, ctx: GraphRunContext[RAGState]) -> End[None]:
        model, _ = get_llm()
        messages = ctx.state.history
        query = await _rewrite_question(ctx.state.question, messages)
        query_embedding = next(get_embeddings().query_embed(query))
        docs = get_vector_store().query(query_embedding, k=5)
        context = _format_context(docs)
        full_prompt = f"{settings.context_prompt.strip()}\n\nRelevant context from the knowledge base:\n\n{context}"
        agent = Agent(
            model,
            system_prompt=full_prompt,
            name="rag_agent",
            capabilities=[ReinjectSystemPrompt(replace_existing=True)],
        )
        result = await asyncio.wait_for(
            agent.run(ctx.state.question, message_history=messages),
            timeout=120.0,
        )
        ctx.state.new_messages = result.new_messages()
        ctx.state.source_docs = _format_sources(docs)
        return End(None)


def get_graph():
    global _graph
    if _graph is not None:
        return _graph

    g = GraphBuilder(state_type=RAGState)

    @g.step
    async def start_step(ctx: StepContext[RAGState, None, None]) -> Route:
        return Route()

    g.add(
        g.node(Route),
        g.node(Chat),
        g.node(Answer),
        g.edge_from(g.start_node).to(start_step),
    )
    _graph = g.build()
    return _graph


async def answer_question(question: str, session_id: str | None = None) -> ChatResponse:
    _, model_name = get_llm()
    try:
        sid = session_id or str(uuid.uuid4())
        history = await load_messages(sid)
        state = RAGState(question=question, history=history)
        await get_graph().run(state=state)
        await save_messages(sid, history + state.new_messages)
        return ChatResponse(
            answer_id=str(uuid.uuid4()),
            answer=_last_output(state.new_messages),
            source_documents=state.source_docs,
            model=model_name,
            session_id=sid,
        )
    except Exception:
        logger.exception("Chat failed for session %s", session_id)
        raise HTTPException(
            status_code=500,
            detail="I encountered an error while processing your request. Please try again.",
        )


async def close() -> None:
    """Close the conversation store connection."""
    global _graph
    _graph = None
    from app.db import conversation_store

    await conversation_store.close()
