"""Answer assembly + streaming runner. The one interface tests cross.

Owns per-task agent assembly, the stream/persist/log pipeline, and history
hydration. Retrieval tools come from rag_tools, intent + filters from
rag_routing.
"""

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.capabilities import ProcessHistory, ReinjectSystemPrompt
from pydantic_ai.exceptions import ModelAPIError, UserError
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.usage import UsageLimits

from app.core.config import settings
from app.db import conversation_store
from app.db.conversation_store import load_messages, save_messages
from app.db.vector_store import get_vector_store
from app.models.schemas import ChatResponse
from app.prompts import get_prompt
from app.retrieval import get_retrieval
from app.services.chat_logging import log_activity, log_chat_message
from app.services.llm import get_llm
from app.services.rag_routing import Deps, _inject_catalog, _route_intent
from app.services.rag_tools import search_documents, search_products, search_shopify_catalog

logger = logging.getLogger(__name__)

# Fallback USD rates for Ollama Cloud (per MTok, off-peak), from
# https://ollama.com/pricing (checked 2026-09-08). genai-prices knows no
# `ollama` provider, so usage.cost is always None for Ollama turns — this
# fills it in for Cloud only. Local runs are $0 by definition and stay None
# (the UI renders None as "—", never $0). Cached-input tokens are billed
# at the input rate: we don't track them separately.
# ponytail: static map; fetch live pricing if Ollama changes rates often.
OLLAMA_CLOUD_RATES: dict[str, tuple[float, float]] = {
    "deepseek-v4-flash": (0.22, 0.66),
    "deepseek-v4-pro": (0.66, 1.98),
    "gemma4": (0.14, 0.40),
    "glm-5.1": (1.00, 3.20),
    "glm-5.2": (1.40, 4.40),
    "glm-5.3": (1.40, 4.40),
    "glm-5.3-flash": (0.15, 0.50),
    "gpt-oss:120b": (0.15, 0.60),
    "gpt-oss:20b": (0.07, 0.30),
    "kimi-k2.6": (0.95, 4.00),
    "kimi-k2.7-code": (0.95, 4.00),
    "kimi-k3": (3.00, 15.00),
    "minimax-m2.7": (0.30, 1.20),
    "minimax-m3": (0.60, 2.40),
    "mistral-large-3": (0.50, 1.50),
    "nemotron-3-nano": (0.06, 0.24),
    "nemotron-3-super": (0.015, 0.60),
    "nemotron-3-ultra": (0.10, 3.00),
    "qwen3.5:397b": (0.60, 3.60),
}


def ollama_cloud_cost(
    model_name: str | None, base_url: str | None, input_tokens: int, output_tokens: int
) -> float | None:
    """USD cost for an Ollama Cloud turn, or None when not billable/known."""
    if not model_name or not base_url:
        return None
    try:
        host = urlparse(base_url if "://" in base_url else f"https://{base_url}").hostname or ""
    except ValueError:
        return None
    if not host.endswith("ollama.com"):
        return None  # local or third-party host: no known price
    key = model_name.split("/", 1)[-1].lower()
    rates = OLLAMA_CLOUD_RATES.get(key)
    if rates is None:
        rates = OLLAMA_CLOUD_RATES.get(key.split(":", 1)[0])  # gemma4:31b-cloud -> gemma4
    if rates is None:
        return None
    in_rate, out_rate = rates
    return input_tokens / 1_000_000 * in_rate + output_tokens / 1_000_000 * out_rate


@dataclass
class RAGState:
    question: str
    intent: str = "docs"
    shopping_out: Any = None
    history: list[ModelMessage] = field(default_factory=list)
    new_messages: list[ModelMessage] = field(default_factory=list)
    conversation_id: str | None = None
    stream: Any = None
    sources: list[str] = field(default_factory=list)
    fallback_reply: str | None = None


class ShoppingAnswer(BaseModel):
    """Shopping agent output: clean prose + indexes into the tool results it recommends.

    No bracketed markers in `answer` — citations travel as data, so no surface
    ever needs marker-stripping."""

    answer: str
    cited_ids: list[int] = []


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


def _extract_followups(full_text: str, *, products_searched: bool, has_cited_products: bool) -> list[str]:
    """Pull the post-search clarifier chip: shopping was invoked but nothing cited.

    Recommend-first: no pre-search branch — the single question path fires only
    after an empty product search, so doc-RAG answers never emit shopping chips.
    RULE 10 caps the model at one question, so at most one chip in document order.
    """
    if has_cited_products or not products_searched:
        return []
    for line in full_text.splitlines():
        # Strip bullet markers only ("- ", "• ", "1. ") — never bare digits ("2 for $10?")
        s = re.sub(r"^\s*(?:[\u2022-]|\d+[.)])\s+", "", line.strip()).strip()
        if s.endswith("?") and 8 < len(s) < 140:
            return [s]
    return []


def _tools(intent: str) -> list:
    """Each task agent only sees its own tools — docs cannot shop, general cannot search."""
    if intent == "shopping":
        return [search_products, search_shopify_catalog]
    if intent == "docs":
        return [search_documents]
    return []


async def _run_agent(state: RAGState, deps: Deps) -> None:
    intent = await _route_intent(deps.model, state.question, deps)
    state.intent = intent
    catalog = await _inject_catalog() if intent == "docs" else ""
    system_prompt = get_prompt(intent, settings.context_prompt.strip(), catalog)
    tools = _tools(intent)
    agent = Agent(
        deps.model,
        system_prompt=system_prompt,
        name=f"{intent}_agent",
        tools=tools,
        output_type=ShoppingAnswer if intent == "shopping" else str,
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
    persist: bool = True,
):
    """Core streaming RAG pipeline. Yields event dicts: text_delta, sources, done, error."""
    t0 = time.perf_counter()
    try:
        model, model_name = get_llm()
    except (UserError, ModelAPIError) as e:
        yield _error_event(e)
        return

    sid = session_id or str(uuid.uuid4())
    history = await load_messages(sid, persist=persist)
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
    cost_usd: float | None = None
    try:
        async with asyncio.timeout(120):
            async with state.stream as result:
                if state.intent == "shopping":
                    # Structured citations: stream the answer field as it validates
                    # (partial mode), cite via data at the end — prose never carries markers.
                    # The last partial is the complete validated output (StreamedRunResult
                    # exposes no .output — stream_output() is the sanctioned reader).
                    sent = 0
                    final_out: ShoppingAnswer | None = None
                    async for partial in result.stream_output(debounce_by=0.1):
                        if isinstance(partial, ShoppingAnswer):
                            final_out = partial
                        text = getattr(partial, "answer", "") or ""
                        if len(text) > sent:
                            delta = text[sent:]
                            sent = len(text)
                            emitted = True
                            answer_parts.append(delta)
                            yield {"type": "text_delta", "content": delta}
                    state.shopping_out = final_out
                else:
                    async for delta in result.stream_text(delta=True):
                        emitted = True
                        answer_parts.append(delta)
                        yield {"type": "text_delta", "content": delta}
                state.new_messages = result.new_messages()
                # Capture token usage like CQA ai_usage_logs (input/output).
                # usage.cost is best-effort USD via genai-prices (None = unpriceable).
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
                        raw_cost = getattr(usage, "cost", None)
                        cost_usd = float(raw_cost) if raw_cost is not None else None
                        if cost_usd is None and settings.ai_provider == "ollama":
                            cost_usd = ollama_cloud_cost(
                                model_name, settings.ollama_base_url, prompt_tokens or 0, completion_tokens or 0
                            )
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
    # Shopping cites via structured output (no markers in prose): validate indexes
    # against tool results, dedupe, keep model order. Other tasks cite nothing.
    cited_products: list[dict] = []
    if state.intent == "shopping":
        out = state.shopping_out
        if isinstance(out, ShoppingAnswer):
            # Orphan-$ scrub: marker-era habit ("much.$[P1]") now surfaces as a
            # trailing "$" with markers gone. $\d prices survive the lookahead.
            clean = re.sub(r"\$(?!\d)", "", out.answer)
            answer_parts = [clean]
            # Structured runs store no TextPart (final message is an output-tool
            # call) — append the prose as a real response or reloads lose the answer.
            state.new_messages.append(ModelResponse(parts=[TextPart(content=clean)]))
            seen: set[int] = set()
            for i in out.cited_ids:
                if 1 <= i <= len(deps.products) and i not in seen:
                    seen.add(i)
                    cited_products.append(deps.products[i - 1])
    # Clarifying chips: shopping invoked but nothing cited (vague query) — the
    # single question path. Recommend-first: no pre-search chips.
    followups = _extract_followups(
        full_text,
        products_searched=deps.products_searched,
        has_cited_products=bool(cited_products),
    )
    # Citation stubs (chunk ids only) ride the response's metadata sidecar — inside the
    # existing messages blob, never sent to the LLM. Titles/refs hydrate from the vector
    # DB at read time so renames always surface. BEFORE save_messages or stubs are lost.
    if state.sources:
        stubs = [{"n": s["n"], "id": s["id"], "pages": s["pages"]} for s in state.sources]
        for m in reversed(state.new_messages):
            if isinstance(m, ModelResponse) and any(isinstance(p, TextPart) for p in m.parts):
                m.metadata = {"sources": stubs}
                break
    await save_messages(sid, history + state.new_messages, persist=persist)
    # --- Durable per-message logs to app.db (like CQA messages + ai_usage_logs) ---
    # Guest (memory-only) threads skip durable logs entirely.
    latency_ms = int((time.perf_counter() - t0) * 1000)
    if persist:
        try:
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
            # Per-turn AI usage row for the cost table (provider/model/tokens/USD).
            try:
                from app.db.session import async_session_factory
                from app.models.unified import AIUsageLog

                async with async_session_factory() as usage_db:
                    usage_db.add(
                        AIUsageLog(
                            provider=settings.ai_provider,
                            model=model_name,
                            input_tokens=prompt_tokens or 0,
                            output_tokens=completion_tokens or 0,
                            cost_usd=cost_usd,
                        )
                    )
                    await usage_db.commit()
            except Exception:
                logger.exception("ai usage log failed sid=%s", sid)
        except Exception:
            logger.exception("chat logging failed sid=%s", sid)
    yield {"type": "sources", "sources": state.sources}
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
    persist: bool = True,
) -> ChatResponse:
    answer = ""
    async for ev in stream_answer(
        question, session_id, user_id=user_id, user_email=user_email, ip_address=ip_address, persist=persist
    ):
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
