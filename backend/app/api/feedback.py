from fastapi import APIRouter, HTTPException
from app.models.schemas import FeedbackRequest, FeedbackResponse
from app.services.feedback import submit_feedback

router = APIRouter()

@router.post("/rating", response_model=FeedbackResponse)
async def rate_response(request: FeedbackRequest):
    try:
        result = await submit_feedback(request)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
