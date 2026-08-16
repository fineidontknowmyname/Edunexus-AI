"""
backend/api/classes.py

Minimal class management — educators create classes, both roles can list them.
Enrollment (class_enrollments) is schema-ready but has no endpoint yet; adding
students to a class is deferred until the student-facing chunks need it.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.api.dependencies import CurrentUser, RequireEducator
from backend.core.database import get_db
from backend.models import schemas
from backend.models.db import Class, ClassContext

router = APIRouter(prefix="/classes", tags=["classes"])

DbDep = Annotated[Session, Depends(get_db)]


@router.post(
    "/",
    response_model=schemas.ClassRead,
    status_code=201,
    summary="Create a class (educator only)",
)
def create_class(
    payload: schemas.ClassCreate,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    class_row = Class(
        name=payload.name,
        subject=payload.subject,
        semester=payload.semester,
        educator_id=current_user.id,
    )
    db.add(class_row)
    db.flush()  # get class_row.id without committing yet

    # Bootstrap an empty ClassContext so ingestion's auto-mark-taught and the
    # future syllabus/assessment endpoints have a row to write to immediately.
    db.add(ClassContext(class_id=class_row.id))

    db.commit()
    db.refresh(class_row)
    return class_row


@router.get(
    "/",
    response_model=list[schemas.ClassRead],
    summary="List classes visible to the current user",
)
def list_classes(db: DbDep, current_user: CurrentUser):
    """
    Educators see classes they teach. Students see classes they're enrolled in
    (via class_enrollments — returns empty until enrollment endpoints exist).
    """
    from backend.models.db import ClassEnrollment, UserRole

    if current_user.role == UserRole.educator:
        return db.query(Class).filter(Class.educator_id == current_user.id).all()

    enrolled_class_ids = (
        db.query(ClassEnrollment.class_id)
        .filter(ClassEnrollment.student_id == current_user.id)
        .subquery()
    )
    return db.query(Class).filter(Class.id.in_(enrolled_class_ids)).all()
