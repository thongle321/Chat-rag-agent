from pydantic import BaseModel, Field


class DocumentIngestResponse(BaseModel):
    status: str
    document_id: str
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


class FeedbackRequest(BaseModel):
    session_id: str | None = None
    answer_id: str
    rating: int = Field(ge=1, le=5)
    comments: str | None = None


class FeedbackResponse(BaseModel):
    status: str
    saved: bool


class DocumentInfo(BaseModel):
    document_id: str
    title: str
    chunks: int


class DocumentListResponse(BaseModel):
    documents: list[DocumentInfo]
