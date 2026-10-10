from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.api import access
from backend.api.dependencies import CurrentUser, RequireEducator, RequireStudent
from backend.core.database import get_db
from backend.services import context_service, insights_service, progress_service, routing_service

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
    return {
        "context": student_context,
        "notes": notes,
        "learning_path": learning_path["path"],
    }
