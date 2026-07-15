import asyncio
import uuid

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.utils.uuid import uuid7
from langgraph.checkpoint.memory import InMemorySaver

from app.core.config import settings
from app.db.vector_store import vector_store
from app.models.schemas import ChatResponse
from app.utils.logger import get_logger

logger = get_logger(__name__)

_checkpointer = InMemorySaver()
_cached_agent = None
_cached_agent_key: str = ""


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


def _get_retriever():
    return vector_store.as_retriever(
        search_type="mmr",
        search_kwargs={"k": 10, "fetch_k": 20},
    )


def _get_agent():
    global _cached_agent, _cached_agent_key

    from langchain_core.tools import tool

    system_msg = settings.context_prompt.strip()
    key = f"{settings.ai_provider}:{settings.ollama_model}:{settings.openai_model}:{system_msg}"

    if _cached_agent is not None and _cached_agent_key == key:
        return _cached_agent

    _last_docs: list = []

    @tool
    def search_documents(query: str) -> str:
        """Search indexed documents for relevant information. Use this to answer questions about uploaded documents."""
        docs = _get_retriever().invoke(query)
        if not docs:
            return "No relevant documents found."
        _last_docs.clear()
        _last_docs.extend(docs)
        parts = []
        for d in docs:
            title = d.metadata.get("title", "unknown")
            page = d.metadata.get("page")
            page_str = f", page {page + 1}" if page is not None else ""
            parts.append(f"[Source: {title}{page_str}]\n{d.page_content}")
        return "\n\n".join(parts)

    def get_last_docs() -> list:
        return list(_last_docs)

    agent = create_agent(
        model=_get_model(),
        tools=[search_documents],
        system_prompt=system_msg,
        checkpointer=_checkpointer,
    )

    _cached_agent = (agent, get_last_docs)
    _cached_agent_key = key
    logger.info("Created new agent for config: %s", key)
    return _cached_agent


async def answer_question(question: str, session_id: str | None = None) -> ChatResponse:
    model_name = _model_display()

    try:
        sid = session_id or str(uuid7())
        agent, get_last_docs = _get_agent()

        result = await asyncio.to_thread(
            agent.invoke,
            {"messages": [{"role": "user", "content": question}]},
            {"configurable": {"thread_id": sid}},
        )

        answer = ""
        for msg in reversed(result["messages"]):
            if hasattr(msg, "content") and msg.content and msg.type == "ai":
                answer = msg.content
                break

        docs = get_last_docs()
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

        return ChatResponse(
            answer_id=str(uuid.uuid4()),
            answer=answer,
            source_documents=sources,
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
