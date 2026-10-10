from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.api import access
from backend.api.dependencies import CurrentUser, RequireEducator
from backend.core.database import get_db
from backend.services import context_service, insights_service

router = APIRouter(prefix="/insights", tags=["insights"])

DbDep = Annotated[Session, Depends(get_db)]


@router.get("/class/{class_id}")
def class_insights(
    class_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    class_row = access.owned_class(db, class_id, current_user)
    subject_id = str(class_row.subject_id) if class_row.subject_id else None
    return {
        "heatmap": insights_service.get_class_heatmap(db, str(class_row.id), subject_id),
        "misconceptions": insights_service.get_common_misconceptions(db, str(class_row.id), subject_id),
        "class_confusion": insights_service.get_class_confusion(db, str(class_row.id), subject_id),
    }


@router.get("/students/at-risk")
def students_at_risk(
    class_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    class_row = access.owned_class(db, class_id, current_user)
    class_context = context_service.assemble_class_context(db, str(class_row.id))
    subject_id = str(class_row.subject_id) if class_row.subject_id else None
    return insights_service.get_at_risk_students(db, str(class_row.id), class_context, subject_id)


@router.get("/questions/trending")
def questions_trending(
    class_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    class_row = access.owned_class(db, class_id, current_user)
    subject_id = str(class_row.subject_id) if class_row.subject_id else None
    return insights_service.get_trending_topics(db, str(class_row.id), subject_id)


@router.get("/flags")
def flagged_responses(
    class_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
    limit: int = 50,
    offset: int = 0,
):
    class_row = access.owned_class(db, class_id, current_user)
    return insights_service.get_flagged_messages(db, str(class_row.id), limit=limit, offset=offset)
