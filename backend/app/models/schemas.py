from pydantic import BaseModel


class DocumentIngestResponse(BaseModel):
    status: str
    message: str


class ChatRequest(BaseModel):
    question: str
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


class DocumentListResponse(BaseModel):
    documents: list[DocumentInfo]


class SessionInfo(BaseModel):
    id: str
    title: str
    message_count: int
    pinned: bool
    created_at: str
    updated_at: str


class SessionMessage(BaseModel):
    role: str
    content: str


class SessionDetail(BaseModel):
    session: SessionInfo
    messages: list[SessionMessage]


class TitleUpdate(BaseModel):
    title: str
