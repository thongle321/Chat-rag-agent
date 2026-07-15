from fastapi import APIRouter
from app.models.schemas import ChatRequest, ChatResponse
from app.services.rag import answer_question

router = APIRouter()

@router.post("/query", response_model=ChatResponse)
async def query_chat(request: ChatRequest):
    return await answer_question(request.question, session_id=request.session_id)
