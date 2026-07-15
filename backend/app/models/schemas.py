from pydantic import BaseModel


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


class DocumentInfo(BaseModel):
    document_id: str
    title: str
    chunks: int


class DocumentListResponse(BaseModel):
    documents: list[DocumentInfo]
