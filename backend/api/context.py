import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api import access
from backend.api.dependencies import CurrentUser, RequireEducator
from backend.core.database import get_db
from backend.models import schemas
from backend.models.db import ClassContext
from backend.services import context_service, insights_service

router = APIRouter(prefix="/context", tags=["context"])

DbDep = Annotated[Session, Depends(get_db)]


def _get_class_context_row(db: Session, class_id) -> ClassContext:
    row = db.query(ClassContext).filter(ClassContext.class_id == class_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Class context not found.")
    return row


@router.get("/class/{class_id}", response_model=schemas.ClassContextRead)
def get_class_context(
    class_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    class_row = access.owned_class(db, class_id, current_user)
    ctx = context_service.assemble_class_context(db, str(class_row.id))
    return {
        "class_id": ctx["class_id"],
        "syllabus": ctx["syllabus"],
        "assessments": ctx["assessments"],
        "teacher_emphasis": ctx["teacher_emphasis"],
    }


@router.patch("/class/{class_id}/syllabus")
def update_syllabus(
    class_id: str,
    payload: schemas.SyllabusUpdate,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    class_row = access.owned_class(db, class_id, current_user)
    row = _get_class_context_row(db, class_row.id)
    syllabus: dict = json.loads(row.syllabus_json) if row.syllabus_json else {}
    syllabus[str(payload.chapter)] = payload.status
    row.syllabus_json = json.dumps(syllabus)
    db.commit()
    return {"syllabus": syllabus}


@router.patch("/class/{class_id}/assessments")
def update_assessments(
    class_id: str,
    payload: schemas.AssessmentsUpdate,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    class_row = access.owned_class(db, class_id, current_user)
    row = _get_class_context_row(db, class_row.id)
    row.assessments_json = json.dumps([a.model_dump() for a in payload.assessments])
    db.commit()
    return {"assessments": [a.model_dump() for a in payload.assessments]}


@router.post("/notes", status_code=201)
def add_note(
    payload: schemas.EducatorNoteCreate,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    class_row = access.owned_student_in_class(db, payload.student_id, payload.class_id, current_user)
    return insights_service.add_educator_note(
        db, str(current_user.id), str(payload.student_id), str(class_row.id), payload.note
    )
