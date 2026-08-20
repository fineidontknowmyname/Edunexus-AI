import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.dependencies import CurrentUser, RequireEducator
from backend.core.database import get_db
from backend.models import schemas
from backend.models.db import Class, ClassContext
from backend.services import context_service

router = APIRouter(prefix="/context", tags=["context"])

DbDep = Annotated[Session, Depends(get_db)]


def _get_class_context_row(db: Session, class_id: str) -> ClassContext:
    row = db.query(ClassContext).filter(ClassContext.class_id == class_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No class context for class '{class_id}'.")
    return row


@router.get("/class/{class_id}", response_model=schemas.ClassContextRead)
def get_class_context(class_id: str, db: DbDep, _educator: Annotated[None, RequireEducator]):
    print(f"[CONTEXT API] Fetching class context for class={class_id}")
    ctx = context_service.assemble_class_context(db, class_id)
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
    _educator: Annotated[None, RequireEducator],
):
    class_row = db.get(Class, class_id)
    if class_row is None:
        raise HTTPException(status_code=404, detail=f"Class '{class_id}' not found.")

    row = _get_class_context_row(db, class_id)
    syllabus: dict = json.loads(row.syllabus_json) if row.syllabus_json else {}
    syllabus[str(payload.chapter)] = payload.status
    row.syllabus_json = json.dumps(syllabus)
    db.commit()
    print(f"[CONTEXT API SUCCESS] class={class_id} chapter={payload.chapter} -> {payload.status}")
    return {"syllabus": syllabus}


@router.patch("/class/{class_id}/assessments")
def update_assessments(
    class_id: str,
    payload: schemas.AssessmentsUpdate,
    db: DbDep,
    _educator: Annotated[None, RequireEducator],
):
    class_row = db.get(Class, class_id)
    if class_row is None:
        raise HTTPException(status_code=404, detail=f"Class '{class_id}' not found.")

    row = _get_class_context_row(db, class_id)
    row.assessments_json = json.dumps([a.model_dump() for a in payload.assessments])
    db.commit()
    print(f"[CONTEXT API SUCCESS] class={class_id} assessments updated: {len(payload.assessments)} entries")
    return {"assessments": [a.model_dump() for a in payload.assessments]}
