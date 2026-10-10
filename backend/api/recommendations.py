from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.api import access
from backend.api.dependencies import CurrentUser, RequireStudent
from backend.core.database import get_db
from backend.models import schemas
from backend.services import context_service, recommendation_service

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

DbDep = Annotated[Session, Depends(get_db)]


@router.get("", response_model=schemas.RecommendationRead)
def get_recommendation(
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
    topic: str = Query(..., min_length=1, max_length=500),
    class_id: str | None = None,
):
    resolved_class_id = access.student_class_id(db, current_user, class_id)
    class_context = context_service.assemble_class_context(db, resolved_class_id)

    from backend.main import app

    embedding_model = getattr(app.state, "embedding_model", None)
    return recommendation_service.get_recommendation(
        db, str(current_user.id), resolved_class_id, class_context["subject_id"], topic, embedding_model
    )
