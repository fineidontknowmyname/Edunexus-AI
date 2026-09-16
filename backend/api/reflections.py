from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.api.dependencies import CurrentUser, RequireEducator, RequireStudent
from backend.core.database import get_db
from backend.models import schemas
from backend.services import reflection_service

router = APIRouter(prefix="/reflections", tags=["reflections"])

DbDep = Annotated[Session, Depends(get_db)]


@router.post("", response_model=schemas.ReflectionRead, status_code=201)
def submit_reflection(
    payload: schemas.ReflectionCreate,
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
):
    print(f"[REFLECTION API] Reflection submitted by student={current_user.id} class={payload.class_id}")
    return reflection_service.submit_reflection(
        db,
        str(current_user.id),
        str(payload.class_id),
        str(payload.subject_id) if payload.subject_id else None,
        payload.topic,
        payload.text,
    )


@router.post("/cluster", response_model=list[schemas.ReflectionClusterRead])
def trigger_clustering(
    class_id: str,
    subject_id: str,
    db: DbDep,
    _educator: Annotated[None, RequireEducator],
):
    from backend.main import app

    embedding_model = getattr(app.state, "embedding_model", None)
    print(f"[REFLECTION API] Clustering triggered for class={class_id} subject={subject_id}")
    return reflection_service.cluster_reflections(db, class_id, subject_id, embedding_model)


@router.get("/clusters", response_model=list[schemas.ReflectionClusterRead])
def read_clusters(
    class_id: str,
    subject_id: str,
    db: DbDep,
    _educator: Annotated[None, RequireEducator],
):
    return reflection_service.get_latest_clusters(db, class_id, subject_id)
