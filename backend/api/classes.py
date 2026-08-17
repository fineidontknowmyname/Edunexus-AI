from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.dependencies import CurrentUser, RequireEducator, RequireStudent
from backend.core.database import get_db
from backend.models import schemas
from backend.models.db import Class, ClassContext, ClassEnrollment

router = APIRouter(prefix="/classes", tags=["classes"])

DbDep = Annotated[Session, Depends(get_db)]


@router.post("/", response_model=schemas.ClassRead, status_code=201)
def create_class(
    payload: schemas.ClassCreate,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    print(f"[CLASSES] Creating class '{payload.name}' for educator {current_user.id}")

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
    print(f"[CLASSES SUCCESS] Class created: id={class_row.id} name='{class_row.name}'")
    return class_row


@router.get("/", response_model=list[schemas.ClassRead])
def list_classes(db: DbDep, current_user: CurrentUser):
    from backend.models.db import UserRole

    if current_user.role == UserRole.educator:
        rows = db.query(Class).filter(Class.educator_id == current_user.id).all()
        print(f"[CLASSES] Educator {current_user.id} owns {len(rows)} class(es)")
        return rows

    enrolled_class_ids = (
        db.query(ClassEnrollment.class_id)
        .filter(ClassEnrollment.student_id == current_user.id)
        .subquery()
    )
    rows = db.query(Class).filter(Class.id.in_(enrolled_class_ids)).all()
    print(f"[CLASSES] Student {current_user.id} enrolled in {len(rows)} class(es)")
    return rows


@router.get("/browse", response_model=list[schemas.ClassRead])
def browse_classes(db: DbDep, _current_user: CurrentUser):
    rows = db.query(Class).all()
    print(f"[CLASSES] Browse — {len(rows)} class(es) exist platform-wide")
    return rows


@router.post("/{class_id}/enroll", response_model=schemas.MessageResponse, status_code=201)
def enroll_in_class(
    class_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
):
    print(f"[CLASSES] Enroll attempt: student={current_user.id} class={class_id}")

    class_row = db.get(Class, class_id)
    if class_row is None:
        print(f"[CLASSES ERROR] Enroll rejected — class '{class_id}' not found.")
        raise HTTPException(status_code=404, detail=f"Class '{class_id}' not found.")

    existing = (
        db.query(ClassEnrollment)
        .filter(ClassEnrollment.class_id == class_id, ClassEnrollment.student_id == current_user.id)
        .first()
    )
    if existing is not None:
        print(f"[CLASSES] Student {current_user.id} already enrolled in class {class_id} — no-op.")
        return {"message": "Already enrolled."}

    db.add(ClassEnrollment(class_id=class_id, student_id=current_user.id))
    db.commit()
    print(f"[CLASSES SUCCESS] Student {current_user.id} enrolled in '{class_row.name}' ({class_id})")
    return {"message": f"Enrolled in '{class_row.name}'."}
