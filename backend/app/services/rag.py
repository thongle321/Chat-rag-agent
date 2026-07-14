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
    from langchain_core.tools import create_retriever_tool

    system_msg = settings.context_prompt.strip()
    retriever_tool = create_retriever_tool(
        _get_retriever(),
        name="search_documents",
        description="Search indexed documents for relevant information. Use this to answer questions about uploaded documents.",
    )
    return create_agent(
        model=_get_model(),
        tools=[retriever_tool],
        system_prompt=system_msg,
        checkpointer=_checkpointer,
    )


async def answer_question(question: str, session_id: str | None = None) -> ChatResponse:
    model_name = _model_display()

    try:
        sid = session_id or str(uuid7())
        agent = _get_agent()

        result = agent.invoke(
            {"messages": [{"role": "user", "content": question}]},
            config={"configurable": {"thread_id": sid}},
        )

        answer = ""
        for msg in reversed(result["messages"]):
            if hasattr(msg, "content") and msg.content and msg.type == "ai":
                answer = msg.content
                break

        docs = _get_retriever().invoke(question)
        sources = list({d.metadata.get("title", "?") for d in docs})

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
