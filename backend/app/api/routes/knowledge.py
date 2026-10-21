from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.deps import get_current_user
from app.models.user import User
from app.schemas.knowledge import HealthTopic, HealthTopicQuestion
from app.services.medlineplus_service import MedicalKnowledgeUnavailable, search_medlineplus

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.post("/search", response_model=list[HealthTopic])
def search_health_topics(
    payload: HealthTopicQuestion,
    response: Response,
    _current_user: User = Depends(get_current_user),
):
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return search_medlineplus(payload.query)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except MedicalKnowledgeUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
