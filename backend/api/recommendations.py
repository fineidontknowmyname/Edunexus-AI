from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.dependencies import CurrentUser, RequireStudent
from backend.core.database import get_db
from backend.models import schemas
from backend.models.db import ClassEnrollment
from backend.services import context_service, recommendation_service

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

DbDep = Annotated[Session, Depends(get_db)]


def _resolve_class_id(db: Session, student_id: str, requested_class_id: str | None) -> str:
    if requested_class_id:
        return requested_class_id
    enrollment = db.query(ClassEnrollment).filter(ClassEnrollment.student_id == student_id).first()
    if enrollment is None:
        raise HTTPException(
            status_code=400,
            detail="Not enrolled in any class. Join one via POST /classes/{class_id}/enroll first.",
        )
    return str(enrollment.class_id)


@router.get("", response_model=schemas.RecommendationRead)
def get_recommendation(
    topic: str,
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
    class_id: str | None = None,
):
    print(f"[RECOMMENDATION API] Requested by student={current_user.id} topic={topic!r}")
    resolved_class_id = _resolve_class_id(db, current_user.id, class_id)
    class_context = context_service.assemble_class_context(db, resolved_class_id)

    from backend.main import app

    embedding_model = getattr(app.state, "embedding_model", None)
    return recommendation_service.get_recommendation(
        db, str(current_user.id), resolved_class_id, class_context["subject_id"], topic, embedding_model
    )
