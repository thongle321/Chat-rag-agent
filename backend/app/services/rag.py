import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException
from pydantic_ai import Agent, RunContext
from pydantic_ai.capabilities import ProcessHistory, ReinjectSystemPrompt
from pydantic_ai.exceptions import ModelAPIError, UserError
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.usage import UsageLimits

from app.core.config import settings
from app.db import conversation_store
from app.db.conversation_store import load_messages, save_messages
from app.db.vector_store import get_vector_store
from app.models.schemas import ChatResponse
from app.retrieval import get_retrieval
from app.services.llm import get_llm
from app.services.products import search_products as _search_products

logger = logging.getLogger(__name__)


@dataclass
class Deps:
    """Runtime deps injected into the graph per-run. Swap in fakes for tests."""

    model: Any
    model_name: str
    retrieval: Any = None
    retrieved: list[dict] = field(default_factory=list)
    products: list[dict] = field(default_factory=list)
    products_searched: bool = False

    def __post_init__(self):
        if self.retrieval is None:
            self.retrieval = get_retrieval()


@dataclass
class RAGState:
    question: str
    history: list[ModelMessage] = field(default_factory=list)
    new_messages: list[ModelMessage] = field(default_factory=list)
    conversation_id: str | None = None
    stream: Any = None
    sources: list[str] = field(default_factory=list)
    fallback_reply: str | None = None


def _format_context(docs: list[dict], nums: list[int]) -> str:
    if not docs:
        return "(No relevant documents found.)"
    parts = []
    for d, n in zip(docs, nums, strict=True):
        meta = d["metadata"]
        title = meta.get("clean_title") or "document"
        page = meta.get("page")
        if page is None:
            page = meta.get("chunk")
        page_str = f", p.{page + 1}" if page is not None else ""
        ref = meta.get("reference")
        ref_str = f" (Ref: {ref})" if ref else ""
        parts.append(f"[{n}] {title}{ref_str}{page_str}\n{d['content']}")
    return "\n\n".join(parts)


async def get_messages(session_id: str) -> list[dict]:
    messages = await load_messages(session_id)
    result = []
    # Citation stubs (chunk ids) were persisted on each response's metadata sidecar;
    # hydrate current titles/refs from the vector DB so renames surface and deleted
    # documents drop out silently.
    stubs_by_index: dict[int, list[dict]] = {}
    all_ids: list[str] = []
    for i, m in enumerate(messages):
        if isinstance(m, ModelResponse) and m.metadata and m.metadata.get("sources"):
            stubs_by_index[i] = m.metadata["sources"]
            all_ids.extend(s.get("id", "") for s in m.metadata["sources"])
    meta_by_id: dict[str, dict] = {}
    if all_ids:
        meta_by_id = await asyncio.to_thread(get_vector_store().get_metadata, all_ids)

    for i, m in enumerate(messages):
        if isinstance(m, ModelRequest):
            for p in m.parts:
                if isinstance(p, UserPromptPart):
                    result.append({"role": "user", "content": p.content})
        elif isinstance(m, ModelResponse):
            for p in m.parts:
                if isinstance(p, TextPart):
                    entry: dict = {"role": "assistant", "content": p.content}
                    sources = [
                        {
                            "n": s["n"],
                            "title": meta.get("clean_title") or "document",
                            "reference": meta.get("reference"),
                            "pages": s.get("pages", []),
                        }
                        for s in stubs_by_index.get(i, [])
                        if (meta := meta_by_id.get(s.get("id", "")))
                    ]
                    if sources:
                        entry["sources"] = sources
                    result.append(entry)
    return result


_MAX_HISTORY = 10


def _keep_recent(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Keep only the last _MAX_HISTORY messages, ensuring history opens with a user turn."""
    recent = messages[-_MAX_HISTORY:]
    while recent and isinstance(recent[0], ModelResponse):
        recent = recent[1:]
    return recent


_CHAT_FALLBACK_REPLY = "Sorry, I'm having trouble right now — please try again!"


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


def _track_sources(deps: Deps, docs: list[dict]) -> list[int]:
    """Register deduplicated citation metadata; return the source number per chunk."""
    nums = []
    for d in docs:
        meta = d["metadata"]
        title = meta.get("clean_title") or "document"
        ref = meta.get("reference")
        entry = next(
            (s for s in deps.retrieved if s["title"] == title and s.get("reference") == ref),
            None,
        )
        if entry is None:
            entry = {
                "n": len(deps.retrieved) + 1,
                "id": d.get("id", ""),
                "title": title,
                "reference": ref,
                "pages": [],
            }
            deps.retrieved.append(entry)
        nums.append(entry["n"])
        page = meta.get("page")
        # ponytail: chunk index stands in for page until real page metadata exists at ingest
        if page is None:
            page = meta.get("chunk")
        if page is not None and page + 1 not in entry["pages"]:
            entry["pages"].append(page + 1)
    return nums


async def search_documents(ctx: RunContext[Deps], query: str) -> str:
    """Search the private knowledge base and return relevant document excerpts.

    Call this when the question may relate to the stored documents, including
    follow-ups (formulate a standalone query yourself). Do NOT call it for
    greetings, small talk, or questions about the assistant itself.

    Args:
        query: A standalone, self-contained search question.
    """
    docs = await asyncio.to_thread(ctx.deps.retrieval.search, query, 8)
    if not docs:
        return "(No relevant documents found.)"
    nums = _track_sources(ctx.deps, docs)
    return _format_context(docs, nums)


def _format_products(prods: list[dict]) -> str:
    if not prods:
        return "(No matching products in catalog.)"
    lines = []
    for i, p in enumerate(prods, 1):
        price = f"{p.get('price')} {p.get('currency', 'USD')}" if p.get("price") is not None else "price on request"
        stock = f", stock {p.get('stock', 0)}" if p.get("stock") is not None else ""
        lines.append(f"[P{i}] {p['name']} — {price}{stock} (id: {p['id']})")
    return "\n".join(lines)


async def search_products(ctx: RunContext[Deps], query: str) -> str:
    """Search the e-commerce product catalog and return matching products.

    Call this when the user asks for recommendations, shopping advice, what to
    buy/eat/use, or anything that could map to a product (e.g. 'What should I
    eat today?'). For vague queries, ask 2-3 short clarifying questions first
    (budget, category, dietary/preference — one per line ending with '?'), then
    call with the refined query. ONLY recommend products returned here
    — never invent SKUs. If no match, say the catalog does not carry it.

    Args:
        query: A standalone product search (e.g. 'spicy lunch under $10').
    """
    prods = await _search_products(query, 6)
    ctx.deps.products = prods
    ctx.deps.products_searched = True
    return _format_products(prods)


def _catalog(docs: list[dict]) -> str:
    if not docs:
        return "No documents in the library yet."
    return "Available documents in the library:\n" + "\n".join(
        f"- {d.get('clean_title') or d.get('title') or 'Document'}"
        + (f" (Ref: {d.get('reference')})" if d.get("reference") else "")
        + f" — {d.get('chunks', 0)} chunks"
        for d in docs
    )


async def _run_agent(state: RAGState, deps: Deps) -> None:
    try:
        docs = await asyncio.wait_for(asyncio.to_thread(deps.retrieval.list_documents), timeout=3.0)
    except Exception:
        logger.warning("Catalog fetch timed out, using fallback", exc_info=True)
        catalog = "Available documents in the library: (catalog temporarily unavailable)"
    else:
        catalog = _catalog(docs)
        logger.info("Catalog injected n=%d", len(docs))
    system_prompt = (
        f"{settings.context_prompt.strip()}\n\n{catalog}\n\n"
        "SHOPPING RULES:\n"
        "9) When the user asks for recommendations, shopping advice, or what to buy/eat/use, "
        "call search_products first. Only recommend products returned by search_products — "
        "cite them as [P1] [P2] matching the numbered products exactly. Never invent products.\n"
        "10) For vague shopping queries (e.g. 'What should I eat today?'), ask 2-3 short "
        "clarifying questions first (budget, category, dietary/preference) — one per line ending "
        "with '?'. Then call search_products with the refined query.\n"
        "11) Sales-oriented but honest: only suggest the top match when search_products "
        "returned it and it fits the clarified need. Organic, unsponsored results ranked on "
        "relevance; the merchant handles payment/fulfillment (you never take payment)."
    )
    agent = Agent(
        deps.model,
        system_prompt=system_prompt,
        name="conversational_rag",
        tools=[search_documents, search_products],
        capabilities=[ProcessHistory(_keep_recent), ReinjectSystemPrompt(replace_existing=True)],
    )
    state.fallback_reply = _CHAT_FALLBACK_REPLY
    state.stream = agent.run_stream(
        state.question,
        message_history=state.history,
        conversation_id=state.conversation_id,
        usage_limits=_RAG_LIMITS,
        deps=deps,
    )


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


async def stream_answer(
    question: str,
    session_id: str | None = None,
    *,
    user_id: str | None = None,
    user_email: str | None = None,
    ip_address: str | None = None,
):
    """Core streaming RAG pipeline. Yields event dicts: text_delta, sources, done, error."""
    t0 = time.perf_counter()
    try:
        model, model_name = get_llm()
    except (UserError, ModelAPIError) as e:
        yield _error_event(e)
        return

    sid = session_id or str(uuid.uuid4())
    history = await load_messages(sid)
    state = RAGState(question=question, history=history, conversation_id=sid)
    deps = Deps(model=model, model_name=model_name, retrieval=get_retrieval())
    try:
        await asyncio.wait_for(_run_agent(state, deps), timeout=120.0)
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
    answer_parts: list[str] = []
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    try:
        async with asyncio.timeout(120):
            async with state.stream as result:
                async for delta in result.stream_text(delta=True):
                    emitted = True
                    answer_parts.append(delta)
                    yield {"type": "text_delta", "content": delta}
                state.new_messages = result.new_messages()
                # Capture token usage like CQA ai_usage_logs (input/output)
                try:
                    usage = (
                        result.usage() if callable(getattr(result, "usage", None)) else getattr(result, "usage", None)
                    )
                    if usage is not None:
                        # Usage object has input_tokens/output_tokens (alias request/response)
                        prompt_tokens = getattr(usage, "input_tokens", None) or getattr(usage, "request_tokens", None)
                        completion_tokens = getattr(usage, "output_tokens", None) or getattr(
                            usage, "response_tokens", None
                        )
                        # Some providers nest details; ensure int or None
                        prompt_tokens = int(prompt_tokens) if prompt_tokens else None
                        completion_tokens = int(completion_tokens) if completion_tokens else None
                except Exception:
                    logger.debug("usage extraction failed", exc_info=True)
                logger.info(
                    "stream done emitted=%s msgs=%d usage=%s/%s",
                    emitted,
                    len(state.new_messages),
                    prompt_tokens,
                    completion_tokens,
                )
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

    # Only surface sources the answer actually cited — retrieval hits are not provenance.
    full_text = "".join(answer_parts)
    cited = {int(m) for m in re.findall(r"\[(\d+)\]", full_text)}
    state.sources = [s for s in deps.retrieved if s["n"] in cited]
    # Products cited as [P1]/[P2] — strict grounding: only IDs returned by tool
    cited_p = {int(m) for m in re.findall(r"\[P(\d+)\]", full_text)}
    cited_products = [p for i, p in enumerate(deps.products, 1) if i in cited_p]
    # Clarifying chips: only when shopping was invoked but nothing was cited —
    # i.e. the query was vague. Structured-ish: prefer budget/category/dietary lines.
    followups: list[str] = []
    if deps.products_searched and not cited_products:
        candidates = []
        for line in full_text.splitlines():
            s = re.sub(r"^[\-\•\d\.\s]+", "", line.strip()).strip()
            if s.endswith("?") and 8 < len(s) < 140:
                candidates.append(s)
        prefer = ("budget", "price", "categor", "type", "diet", "prefer", "flavor", "flavour", "size")
        ranked = sorted(candidates, key=lambda q: not any(w in q.lower() for w in prefer))
        followups = ranked[:3]
    if state.sources:
        # Persist citation stubs (chunk ids only) on the response's metadata sidecar —
        # rides inside the existing messages blob, never sent to the LLM. Titles/refs
        # hydrate from the vector DB at read time so renames always surface.
        # Must happen BEFORE save_messages or the stored blob lacks the stubs.
        stubs = [{"n": s["n"], "id": s["id"], "pages": s["pages"]} for s in state.sources]
        for m in reversed(state.new_messages):
            if isinstance(m, ModelResponse) and any(isinstance(p, TextPart) for p in m.parts):
                m.metadata = {"sources": stubs}
                break
    await save_messages(sid, history + state.new_messages)
    # --- Durable per-message logs to app.db (like CQA messages + ai_usage_logs) ---
    latency_ms = int((time.perf_counter() - t0) * 1000)
    try:
        from app.services.chat_logging import log_activity, log_chat_message

        answer_text = "".join(answer_parts)
        # user turn
        await log_chat_message(
            session_id=sid,
            role="user",
            content=question,
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
        )
        # assistant turn — keep forever, no TTL (mirrors CQA messages + ai_usage_logs)
        await log_chat_message(
            session_id=sid,
            role="assistant",
            content=answer_text,
            user_id=user_id,
            user_email=user_email,
            model=model_name,
            sources=state.sources,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            ip_address=ip_address,
        )
        await log_activity(
            action="chat.query",
            user_id=user_id,
            user_email=user_email,
            resource_type="session",
            resource_id=sid,
            detail=json.dumps(
                {
                    "model": model_name,
                    "sources_n": len(state.sources),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                },
                ensure_ascii=False,
            ),
            ip_address=ip_address,
        )
    except Exception:
        logger.exception("chat logging failed sid=%s", sid)
    yield {"type": "sources", "sources": state.sources}
    if cited_products:
        yield {"type": "products", "products": cited_products}
    if followups:
        yield {"type": "followups", "followups": followups}
    yield {"type": "done", "session_id": sid, "model": model_name}


async def answer_question(
    question: str,
    session_id: str | None = None,
    *,
    user_id: str | None = None,
    user_email: str | None = None,
    ip_address: str | None = None,
) -> ChatResponse:
    answer = ""
    async for ev in stream_answer(question, session_id, user_id=user_id, user_email=user_email, ip_address=ip_address):
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
    await conversation_store.close()
