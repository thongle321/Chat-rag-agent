from typing import Literal

from pydantic import BaseModel, Field


class DocumentIngestResponse(BaseModel):
    status: Literal["ok", "error"]
    message: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    session_id: str | None = None


class ChatResponse(BaseModel):
    answer_id: str
    answer: str
    source_documents: list[str]
    model: str
    session_id: str


class DocumentInfo(BaseModel):
    document_id: str
    title: str
    chunks: int
    size: int


class DocumentListResponse(BaseModel):
    documents: list[DocumentInfo]


class SessionMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class SessionDetail(BaseModel):
    messages: list[SessionMessage]


class StatsResponse(BaseModel):
    total_documents: int
    total_chunks: int
    total_sessions: int
    total_queries: int
