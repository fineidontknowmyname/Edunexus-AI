from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.dependencies import CurrentUser, RequireEducator, RequireStudent
from backend.core.database import get_db
from backend.models.db import ClassEnrollment
from backend.services import context_service, insights_service, progress_service, routing_service

router = APIRouter(prefix="/progress", tags=["progress"])

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


@router.get("/dashboard")
def dashboard(
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
    class_id: str | None = None,
):
    print(f"[PROGRESS API] Dashboard requested by student={current_user.id}")
    resolved_class_id = _resolve_class_id(db, current_user.id, class_id)
    return progress_service.get_dashboard(db, str(current_user.id), resolved_class_id)


@router.get("/path")
def path(
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
    class_id: str | None = None,
):
    print(f"[PROGRESS API] Learning path requested by student={current_user.id}")
    resolved_class_id = _resolve_class_id(db, current_user.id, class_id)
    return progress_service.get_learning_path(db, str(current_user.id), resolved_class_id)


@router.get("/routing")
def routing(
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
    class_id: str | None = None,
):
    print(f"[PROGRESS API] Routing map requested by student={current_user.id}")
    resolved_class_id = _resolve_class_id(db, current_user.id, class_id)
    return routing_service.get_routing_map(db, str(current_user.id), resolved_class_id)


@router.get("/student/{student_id}")
def student_full_context(
    student_id: str,
    class_id: str,
    db: DbDep,
    _educator: Annotated[None, RequireEducator],
):
    print(f"[PROGRESS API] Full student context requested for student={student_id} class={class_id}")
    student_context = context_service.assemble_student_context(db, student_id, class_id)
    notes = insights_service.get_educator_notes(db, student_id, class_id)
    learning_path = progress_service.get_learning_path(db, student_id, class_id)
    return {
        "context": student_context,
        "notes": notes,
        "learning_path": learning_path["path"],
    }
