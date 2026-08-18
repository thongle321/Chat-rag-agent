import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel
from pydantic_ai import Agent
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


class RouteResult(BaseModel):
    category: Literal["chat", "answer"]


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


# ponytail: three-node graph (route -> chat|answer) — add re-rank, self-verify nodes when multistep logic lands
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


def _format_sources(docs: list[dict]) -> list[str]:
    pages_by_title: dict[str, set[int]] = {}
    refs_by_title: dict[str, str | None] = {}
    for d in docs:
        meta = d["metadata"]
        title = meta.get("clean_title") or "document"
        reference = meta.get("reference")
        page = meta.get("page")
        if title not in pages_by_title:
            pages_by_title[title] = set()
            refs_by_title[title] = reference
        else:
            refs_by_title[title] = refs_by_title[title] or reference
        if page is not None:
            pages_by_title[title].add(page + 1)
    sources = []
    for title in sorted(pages_by_title.keys()):
        pages = pages_by_title[title]
        reference = refs_by_title[title]
        if pages:
            ref = reference or ""
            if ref:
                sources.append(f"{title} (Ref: {ref}) (p{', p'.join(str(p) for p in sorted(pages))})")
            else:
                sources.append(f"{title} (p{', p'.join(str(p) for p in sorted(pages))})")
        else:
            sources.append(title if not ref else f"{title} (Ref: {ref})")
    return sources


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

_SINGLE_SHOT_LIMITS = UsageLimits(request_limit=3)
_RAG_LIMITS = UsageLimits(request_limit=3)


async def _rewrite_question(
    question: str, messages: list[ModelMessage], deps: Deps, conversation_id: str | None = None
) -> str:
    if not messages:
        return question
    agent = Agent(
        deps.model,
        system_prompt=REWRITE_PROMPT,
        name="rewrite",
        capabilities=[ProcessHistory(_keep_recent), ReinjectSystemPrompt(replace_existing=True)],
    )
    result = await asyncio.wait_for(
        agent.run(
            question,
            message_history=messages,
            conversation_id=conversation_id,
            usage_limits=_SINGLE_SHOT_LIMITS,
        ),
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
class Route(BaseNode[RAGState, Deps]):
    async def run(self, ctx: GraphRunContext[RAGState, Deps]) -> "Chat | Answer":
        router = Agent(
            ctx.deps.model,
            output_type=RouteResult,
            system_prompt=ROUTER_PROMPT,
            name="router",
            capabilities=[ProcessHistory(_keep_recent), ReinjectSystemPrompt(replace_existing=True)],
        )
        result = await asyncio.wait_for(
            router.run(
                ctx.state.question,
                message_history=ctx.state.history,
                conversation_id=ctx.state.conversation_id,
                usage_limits=_SINGLE_SHOT_LIMITS,
            ),
            timeout=30.0,
        )
        return Chat() if result.output.category == "chat" else Answer()


@dataclass
class Chat(BaseNode[RAGState, Deps, None]):
    async def run(self, ctx: GraphRunContext[RAGState, Deps]) -> End[None]:
        docs = [d for d in await asyncio.to_thread(ctx.deps.vector_store.list_documents) if d.get("summary")]
        prompt = settings.chat_prompt.strip()
        if docs:
            listing = "\n".join(
                f"- {d.get('clean_title') or 'Document'} "
                f": {d['summary']}"
                + (f" (Ref: {d.get('reference')})" if d.get('reference') else "")
                for d in docs
            )
            prompt += f"\n\nAvailable documents:\n{listing}"
        agent = Agent(
            ctx.deps.model,
            system_prompt=prompt,
            name="chat_agent",
            capabilities=[ProcessHistory(_keep_recent), ReinjectSystemPrompt(replace_existing=True)],
        )
        ctx.state.fallback_reply = _CHAT_FALLBACK_REPLY
        ctx.state.stream = agent.run_stream(
            ctx.state.question,
            message_history=ctx.state.history,
            conversation_id=ctx.state.conversation_id,
            usage_limits=_RAG_LIMITS,
        )
        return End(None)


@dataclass
class Answer(BaseNode[RAGState, Deps, None]):
    async def run(self, ctx: GraphRunContext[RAGState, Deps]) -> End[None]:
        messages = ctx.state.history
        query = await _rewrite_question(ctx.state.question, messages, ctx.deps, ctx.state.conversation_id)
        query_embedding = await asyncio.to_thread(
            lambda: next(get_embeddings().query_embed(query_prefix() + query))
        )
        docs = await asyncio.to_thread(ctx.deps.vector_store.hybrid_query, query, query_embedding, 8)
        context = _format_context(docs)
        full_prompt = f"{settings.context_prompt.strip()}\n\nRelevant context from the knowledge base:\n\n{context}"
        agent = Agent(
            ctx.deps.model,
            system_prompt=full_prompt,
            name="rag_agent",
            capabilities=[ProcessHistory(_keep_recent), ReinjectSystemPrompt(replace_existing=True)],
        )
        ctx.state.sources = _format_sources(docs)
        ctx.state.stream = agent.run_stream(
            ctx.state.question,
            message_history=messages,
            conversation_id=ctx.state.conversation_id,
            usage_limits=_RAG_LIMITS,
        )
        return End(None)


def get_graph():
    global _graph
    if _graph is not None:
        return _graph

    g = GraphBuilder(state_type=RAGState, deps_type=Deps)

    @g.step
    async def start_step(ctx: StepContext[RAGState, Deps, None]) -> Route:
        return Route()

    g.add(
        g.node(Route),
        g.node(Chat),
        g.node(Answer),
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
                async for delta in result.stream_text():
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
