from fastapi import APIRouter, HTTPException
from app.models.schemas import ChatRequest, ChatResponse
from app.services.rag import answer_question

router = APIRouter()


@router.post("/query", response_model=ChatResponse)
async def query_chat(request: ChatRequest):
    try:
        answer = await answer_question(request.question, session_id=request.session_id)
        return answer
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
