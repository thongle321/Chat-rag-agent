import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException
from pydantic_ai import Agent, RunContext
from pydantic_ai.capabilities import ProcessHistory, ReinjectSystemPrompt
from pydantic_ai.exceptions import ModelAPIError, UserError
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.usage import UsageLimits
from pydantic_graph import BaseNode, End, GraphBuilder, GraphRunContext, StepContext

from app.core.config import settings
from app.db.conversation_store import load_messages, save_messages
from app.db.embeddings import get_embeddings, query_prefix
from app.db.vector_store import VectorStore, get_vector_store
from app.models.schemas import ChatResponse
from app.services.llm import get_llm

logger = logging.getLogger(__name__)


@dataclass
class Deps:
    """Runtime deps injected into the graph per-run. Swap in fakes for tests."""

    model: Any
    model_name: str
    vector_store: VectorStore


@dataclass
class RAGState:
    question: str
    history: list[ModelMessage] = field(default_factory=list)
    new_messages: list[ModelMessage] = field(default_factory=list)
    conversation_id: str | None = None
    stream: Any = None
    sources: list[str] = field(default_factory=list)
    fallback_reply: str | None = None


# ponytail: single-node graph kept only to preserve the streaming plumbing; collapse to a
# plain function if the graph ever stops earning its keep.
_graph = None


def _format_context(docs: list[dict]) -> str:
    if not docs:
        return "(No relevant documents found.)"
    parts = []
    for d in docs:
        meta = d["metadata"]
        title = meta.get("clean_title") or "document"
        page = meta.get("page")
        page_str = f", p.{page + 1}" if page is not None else ""
        ref = meta.get("reference")
        ref_str = f" (Ref: {ref})" if ref else ""
        parts.append(f"[Source: {title}{ref_str}{page_str}]\n{d['content']}")
    return "\n\n".join(parts)


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


_MAX_HISTORY = 10


def _keep_recent(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Keep only the last _MAX_HISTORY messages, ensuring history opens with a user turn."""
    recent = messages[-_MAX_HISTORY:]
    while recent and isinstance(recent[0], ModelResponse):
        recent = recent[1:]
    return recent


_CHAT_FALLBACK_REPLY = (
    "Sorry, I'm having trouble right now — please try again!"
)


def _model_error_reason(e: ModelAPIError) -> str | None:
    """Extract the human-readable provider message from a model API error."""
    body = getattr(e, "body", None)
    if isinstance(body, dict):
        inner = body.get("error")
        if isinstance(inner, dict) and inner.get("message"):
            return str(inner["message"])
        if body.get("message"):
            return str(body["message"])
    return None

_RAG_LIMITS = UsageLimits(request_limit=3)


async def search_documents(ctx: RunContext[Deps], query: str) -> str:
    """Search the private knowledge base and return relevant document excerpts.

    Call this when the question may relate to the stored documents, including
    follow-ups (formulate a standalone query yourself). Do NOT call it for
    greetings, small talk, or questions about the assistant itself.

    Args:
        query: A standalone, self-contained search question.
    """
    query_embedding = await asyncio.to_thread(
        lambda: next(get_embeddings().query_embed(query_prefix() + query))
    )
    docs = await asyncio.to_thread(ctx.deps.vector_store.hybrid_query, query, query_embedding, 8)
    # ponytail: no relevance threshold — RRF scores aren't cosine similarity, so the model
    # judges relevance from content. Add a dense-only cosine gate if false positives appear.
    return _format_context(docs)


@dataclass
class RunAgent(BaseNode[RAGState, Deps, None]):
    async def run(self, ctx: GraphRunContext[RAGState, Deps]) -> End[None]:
        agent = Agent(
            ctx.deps.model,
            system_prompt=settings.context_prompt.strip(),
            name="conversational_rag",
            tools=[search_documents],
            capabilities=[ProcessHistory(_keep_recent), ReinjectSystemPrompt(replace_existing=True)],
        )
        ctx.state.fallback_reply = _CHAT_FALLBACK_REPLY
        ctx.state.stream = agent.run_stream(
            ctx.state.question,
            message_history=ctx.state.history,
            conversation_id=ctx.state.conversation_id,
            usage_limits=_RAG_LIMITS,
            deps=ctx.deps,
        )
        return End(None)


def get_graph():
    global _graph
    if _graph is not None:
        return _graph

    g = GraphBuilder(state_type=RAGState, deps_type=Deps)

    @g.step
    async def start_step(ctx: StepContext[RAGState, Deps, None]) -> RunAgent:
        return RunAgent()

    g.add(
        g.node(RunAgent),
        g.edge_from(g.start_node).to(start_step),
    )
    _graph = g.build()
    return _graph


def _error_event(e: Exception) -> dict:
    if isinstance(e, ModelAPIError):
        reason = _model_error_reason(e)
        if reason:
            return {"type": "error", "status_code": 502, "detail": reason[:300]}
        status = getattr(e, "status_code", None)
        return {
            "type": "error",
            "status_code": 502,
            "detail": (
                f"AI model '{e.model_name}' returned an error"
                + (f" (HTTP {status})" if status else "")
                + ". Check your AI provider settings or subscription."
            ),
        }
    if isinstance(e, TimeoutError):
        return {"type": "error", "status_code": 504, "detail": "Request took too long. Please try again."}
    logger.exception("Chat failed")
    return {
        "type": "error",
        "status_code": 500,
        "detail": "I encountered an error while processing your request. Please try again.",
    }


async def stream_answer(question: str, session_id: str | None = None):
    """Core streaming RAG pipeline. Yields event dicts: text_delta, sources, done, error."""
    try:
        model, model_name = get_llm()
    except (UserError, ModelAPIError) as e:
        yield _error_event(e)
        return

    sid = session_id or str(uuid.uuid4())
    history = await load_messages(sid)
    state = RAGState(question=question, history=history, conversation_id=sid)
    deps = Deps(model=model, model_name=model_name, vector_store=get_vector_store())
    try:
        await asyncio.wait_for(get_graph().run(state=state, deps=deps), timeout=120.0)
    except UserError:
        logger.warning("AI provider misconfigured for session %s", sid)
        yield {
            "type": "error",
            "status_code": 502,
            "detail": "AI provider is not configured correctly. Add the API key for your provider in Settings.",
        }
        return
    except Exception as e:
        yield _error_event(e)
        return

    emitted = False
    try:
        async with asyncio.timeout(120):
            async with state.stream as result:
                async for delta in result.stream_text(delta=True):
                    emitted = True
                    yield {"type": "text_delta", "content": delta}
                state.new_messages = result.new_messages()
    except Exception as e:
        if state.fallback_reply and not emitted:
            state.new_messages = [
                ModelRequest(parts=[UserPromptPart(content=state.question)]),
                ModelResponse(parts=[TextPart(content=state.fallback_reply)]),
            ]
            yield {"type": "text_delta", "content": state.fallback_reply}
        else:
            yield _error_event(e)
            return

    await save_messages(sid, history + state.new_messages)
    yield {"type": "sources", "sources": state.sources}
    yield {"type": "done", "session_id": sid, "model": model_name}


async def answer_question(question: str, session_id: str | None = None) -> ChatResponse:
    answer = ""
    async for ev in stream_answer(question, session_id):
        if ev["type"] == "text_delta":
            answer += ev["content"]
        elif ev["type"] == "error":
            raise HTTPException(status_code=ev["status_code"], detail=ev["detail"])
        elif ev["type"] == "done":
            return ChatResponse(
                answer_id=str(uuid.uuid4()),
                answer=answer,
                model=ev["model"],
                session_id=ev["session_id"],
            )
    raise HTTPException(status_code=500, detail="Stream ended without a response.")


async def close() -> None:
    """Close the conversation store connection."""
    global _graph
    _graph = None
    from app.db import conversation_store

    await conversation_store.close()
