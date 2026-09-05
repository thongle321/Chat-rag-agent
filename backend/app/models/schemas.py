from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DocumentIngestResponse(BaseModel):
    status: Literal["ok", "error"]
    message: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


class ChatResponse(BaseModel):
    answer_id: str
    answer: str
    model: str
    session_id: str


class DocumentInfo(BaseModel):
    document_id: str
    title: str
    chunks: int
    size: int


class DocumentListResponse(BaseModel):
    documents: list[DocumentInfo]


class SessionSource(BaseModel):
    n: int
    title: str
    reference: str | None = None
    pages: list[int] = []


class SessionMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    sources: list[SessionSource] | None = None


class SessionDetail(BaseModel):
    messages: list[SessionMessage]


class SessionListItem(BaseModel):
    id: str
    title: str
    pinned: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SessionPatch(BaseModel):
    title: str | None = None
    pinned: bool | None = None


class StatsResponse(BaseModel):
    total_documents: int
    total_chunks: int
    total_sessions: int
    total_queries: int
