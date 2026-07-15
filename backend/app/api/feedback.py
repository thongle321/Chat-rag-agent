from fastapi import APIRouter
from app.models.schemas import FeedbackRequest, FeedbackResponse
from app.services.feedback import submit_feedback

router = APIRouter()

@router.post("/rating", response_model=FeedbackResponse)
async def rate_response(request: FeedbackRequest):
    return await submit_feedback(request)
