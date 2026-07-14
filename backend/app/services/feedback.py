import json
import threading
from pathlib import Path

from app.core.config import settings
from app.models.schemas import FeedbackRequest, FeedbackResponse

_feedback_lock = threading.Lock()


def _get_feedback_path() -> Path:
    return Path(settings.upload_dir) / "feedback.json"


async def submit_feedback(request: FeedbackRequest) -> FeedbackResponse:
    record = {
        "session_id": request.session_id,
        "answer_id": request.answer_id,
        "rating": request.rating,
        "comments": request.comments,
    }

    feedback_path = _get_feedback_path()
    feedback_path.parent.mkdir(parents=True, exist_ok=True)

    with _feedback_lock:
        existing = []
        if feedback_path.exists():
            try:
                existing = json.loads(feedback_path.read_text())
            except json.JSONDecodeError:
                existing = []
        existing.append(record)
        feedback_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))

    return FeedbackResponse(status="saved", saved=True)
