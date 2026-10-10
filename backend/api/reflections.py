from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api import access
from backend.api.dependencies import CurrentUser, RequireEducator, RequireStudent
from backend.core.database import get_db
from backend.core.rate_limit import rate_limit
from backend.models import schemas
from backend.services import reflection_service

router = APIRouter(prefix="/reflections", tags=["reflections"])

DbDep = Annotated[Session, Depends(get_db)]
ReflectionRateLimit = Depends(rate_limit("reflection-submit", max_requests=10, window_seconds=600))
ClusterRateLimit = Depends(rate_limit("reflection-cluster", max_requests=10, window_seconds=600))


@router.post("", response_model=schemas.ReflectionRead, status_code=201, dependencies=[ReflectionRateLimit])
def submit_reflection(
    payload: schemas.ReflectionCreate,
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
):
    class_row = access.enrolled_class(db, payload.class_id, current_user)
    subject_id = class_row.subject_id
    if payload.subject_id and class_row.subject_id and str(payload.subject_id) != str(class_row.subject_id):
        raise HTTPException(status_code=400, detail="That subject doesn't belong to this class.")
    return reflection_service.submit_reflection(
        db,
        str(current_user.id),
        str(class_row.id),
        str(subject_id) if subject_id else None,
        payload.topic,
        payload.text,
    )


@router.post("/cluster", response_model=list[schemas.ReflectionClusterRead], dependencies=[ClusterRateLimit])
def trigger_clustering(
    class_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
    subject_id: str | None = None,
):
    class_row = access.owned_class(db, class_id, current_user)
    resolved_subject = subject_id or (str(class_row.subject_id) if class_row.subject_id else None)
    if resolved_subject is None:
        raise HTTPException(status_code=400, detail="This class has no subject, so there is nothing to cluster.")

    from backend.main import app

    embedding_model = getattr(app.state, "embedding_model", None)
    return reflection_service.cluster_reflections(db, str(class_row.id), resolved_subject, embedding_model)


@router.get("/clusters", response_model=list[schemas.ReflectionClusterRead])
def read_clusters(
    class_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
    subject_id: str | None = None,
):
    class_row = access.owned_class(db, class_id, current_user)
    resolved_subject = subject_id or (str(class_row.subject_id) if class_row.subject_id else None)
    if resolved_subject is None:
        return []
    return reflection_service.get_latest_clusters(db, str(class_row.id), resolved_subject)
