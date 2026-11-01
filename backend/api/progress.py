from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.api import access
from backend.api.dependencies import CurrentUser, RequireEducator, RequireStudent
from backend.core.database import get_db
from backend.models import schemas
from backend.models.db import Quiz, QuizAttempt
from backend.services import context_service, insights_service, progress_service, recommendation_service, routing_service

router = APIRouter(prefix="/progress", tags=["progress"])

DbDep = Annotated[Session, Depends(get_db)]


@router.get("/dashboard")
def dashboard(
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
    class_id: str | None = None,
):
    resolved_class_id = access.student_class_id(db, current_user, class_id)
    return progress_service.get_dashboard(db, str(current_user.id), resolved_class_id)


@router.get("/path")
def path(
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
    class_id: str | None = None,
):
    resolved_class_id = access.student_class_id(db, current_user, class_id)
    return progress_service.get_learning_path(db, str(current_user.id), resolved_class_id)


@router.get("/routing")
def routing(
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
    class_id: str | None = None,
):
    resolved_class_id = access.student_class_id(db, current_user, class_id)
    return routing_service.get_routing_map(db, str(current_user.id), resolved_class_id)


@router.get("/recommendations", response_model=schemas.ProgressRecommendationsResponse)
def progress_recommendations(
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
    class_id: str | None = None,
):
    """
    Returns personalized learning recommendations directly on the student Progress page
    based on empirical assessment performance.
    """
    resolved_class_id = access.student_class_id(db, current_user, class_id)
    return recommendation_service.get_progress_recommendations(
        db, str(current_user.id), resolved_class_id
    )


@router.get("/student/{student_id}")
def student_full_context(
    student_id: str,
    class_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    class_row = access.owned_student_in_class(db, student_id, class_id, current_user)
    student_context = context_service.assemble_student_context(db, student_id, str(class_row.id))
    notes = insights_service.get_educator_notes(db, student_id, str(class_row.id))
    learning_path = progress_service.get_learning_path(db, student_id, str(class_row.id))

    attempts = (
        db.query(QuizAttempt, Quiz.title)
        .join(Quiz, QuizAttempt.quiz_id == Quiz.id)
        .filter(QuizAttempt.student_id == student_id, Quiz.class_id == class_row.id)
        .order_by(QuizAttempt.started_at.desc())
        .limit(20)
        .all()
    )
    attempts_out = [
        {
            "id": str(att.id),
            "quiz_id": str(att.quiz_id),
            "quiz_title": title,
            "score": att.score,
            "score_ratio": round(att.score / 100.0, 4) if att.score is not None else None,
            "completed": att.completed,
            "started_at": att.started_at.isoformat() if att.started_at else None,
            "completed_at": att.completed_at.isoformat() if att.completed_at else None,
        }
        for att, title in attempts
    ]

    return {
        "context": student_context,
        "notes": notes,
        "learning_path": learning_path["path"],
        "attempts": attempts_out,
    }
