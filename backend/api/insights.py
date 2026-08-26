from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.api.dependencies import RequireEducator
from backend.core.database import get_db
from backend.services import context_service, insights_service

router = APIRouter(prefix="/insights", tags=["insights"])

DbDep = Annotated[Session, Depends(get_db)]


@router.get("/class/{class_id}")
def class_insights(class_id: str, db: DbDep, _educator: Annotated[None, RequireEducator]):
    print(f"[INSIGHTS API] Class insights requested for class={class_id}")
    return {
        "heatmap": insights_service.get_class_heatmap(db, class_id),
        "misconceptions": insights_service.get_common_misconceptions(db, class_id),
    }


@router.get("/students/at-risk")
def students_at_risk(class_id: str, db: DbDep, _educator: Annotated[None, RequireEducator]):
    class_context = context_service.assemble_class_context(db, class_id)
    return insights_service.get_at_risk_students(db, class_id, class_context)


@router.get("/questions/trending")
def questions_trending(class_id: str, db: DbDep, _educator: Annotated[None, RequireEducator]):
    return insights_service.get_trending_topics(db, class_id)


@router.get("/flags")
def flagged_responses(class_id: str, db: DbDep, _educator: Annotated[None, RequireEducator]):
    return insights_service.get_flagged_messages(db, class_id)
