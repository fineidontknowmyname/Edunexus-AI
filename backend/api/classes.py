from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.api.dependencies import CurrentUser, RequireEducator
from backend.core.database import get_db
from backend.models import schemas
from backend.models.db import Class, ClassContext

router = APIRouter(prefix="/classes", tags=["classes"])

DbDep = Annotated[Session, Depends(get_db)]


@router.post("/", response_model=schemas.ClassRead, status_code=201)
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
    db.flush()

    db.add(ClassContext(class_id=class_row.id))

    db.commit()
    db.refresh(class_row)
    return class_row


@router.get("/", response_model=list[schemas.ClassRead])
def list_classes(db: DbDep, current_user: CurrentUser):
    from backend.models.db import ClassEnrollment, UserRole

    if current_user.role == UserRole.educator:
        return db.query(Class).filter(Class.educator_id == current_user.id).all()

    enrolled_class_ids = (
        db.query(ClassEnrollment.class_id)
        .filter(ClassEnrollment.student_id == current_user.id)
        .subquery()
    )
    return db.query(Class).filter(Class.id.in_(enrolled_class_ids)).all()
