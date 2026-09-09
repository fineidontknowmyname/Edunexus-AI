import logging
import os
import tempfile
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.api.dependencies import CurrentUser, RequireEducator
from backend.core.database import get_db
from backend.models import schemas
from backend.models.db import Chunk, Document
from backend.pipeline.parser import SUPPORTED_EXTENSIONS, extract_text
from backend.services import subject_service, topic_graph_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["subjects"])
DbDep = Annotated[Session, Depends(get_db)]


# --------------------------------------------------------------------------- #
# Categories
# --------------------------------------------------------------------------- #


@router.post("/categories", response_model=schemas.CategoryRead, status_code=201)
def create_category(
    payload: schemas.CategoryCreate,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    return subject_service.create_category(db, payload.name, str(current_user.id))


@router.get("/categories", response_model=list[schemas.CategoryRead])
def list_categories(db: DbDep, _user: CurrentUser):
    return subject_service.list_categories(db)


# --------------------------------------------------------------------------- #
# Subjects
# --------------------------------------------------------------------------- #


@router.post("/subjects", response_model=schemas.SubjectRead, status_code=201)
def create_subject(
    payload: schemas.SubjectCreate,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    try:
        return subject_service.create_subject(
            db, payload.name, str(payload.category_id), str(current_user.id)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/subjects", response_model=list[schemas.SubjectRead])
def list_subjects(db: DbDep, _user: CurrentUser):
    return subject_service.list_subjects(db)


@router.post("/subjects/{subject_id}/syllabus")
async def draft_topic_graph(
    subject_id: str,
    db: DbDep,
    _educator: Annotated[None, RequireEducator],
    file: UploadFile = File(...),
):
    """Parse an uploaded syllabus and return an AI-drafted Topic Graph. Nothing is
    written to the database until the educator confirms via PUT /topic-graph."""
    if subject_service.get_subject(db, subject_id) is None:
        raise HTTPException(status_code=404, detail=f"Subject '{subject_id}' not found.")

    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{ext}'.")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    try:
        tmp.write(await file.read())
        tmp.flush()
        tmp.close()
        syllabus_text = extract_text(file_path=tmp.name, filename=filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        if os.path.exists(tmp.name):
            os.remove(tmp.name)

    try:
        topics = await topic_graph_service.draft_from_syllabus(syllabus_text)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"Topic drafting failed: {exc}")

    return {"subject_id": subject_id, "topics": topics}


@router.get("/subjects/{subject_id}/topic-graph")
def read_topic_graph(subject_id: str, db: DbDep, _user: CurrentUser):
    if subject_service.get_subject(db, subject_id) is None:
        raise HTTPException(status_code=404, detail=f"Subject '{subject_id}' not found.")
    return {"subject_id": subject_id, "topics": topic_graph_service.read_graph(db, subject_id)}


@router.put("/subjects/{subject_id}/topic-graph")
def confirm_topic_graph(
    subject_id: str,
    payload: schemas.TopicGraphConfirm,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    try:
        rows = topic_graph_service.confirm(
            db,
            subject_id,
            [t.model_dump() for t in payload.topics],
            str(current_user.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"subject_id": subject_id, "topic_count": len(rows)}


@router.patch("/subjects/{subject_id}/topics")
def rename_topic(
    subject_id: str,
    payload: schemas.TopicRename,
    db: DbDep,
    _educator: Annotated[None, RequireEducator],
):
    try:
        topic_graph_service.rename_topic(db, subject_id, payload.old_topic, payload.new_topic)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"subject_id": subject_id, "renamed_to": payload.new_topic}


@router.get("/subjects/{subject_id}/unclassified", response_model=list[schemas.UnclassifiedChunk])
def list_unclassified(subject_id: str, db: DbDep, _educator: Annotated[None, RequireEducator]):
    rows = (
        db.query(Chunk, Document.title)
        .join(Document, Chunk.document_id == Document.id)
        .filter(
            Chunk.subject_id == subject_id,
            Chunk.topic.is_(None),
            Document.deleted == False,  # noqa: E712
        )
        .order_by(Document.title, Chunk.chunk_index)
        .all()
    )
    return [
        schemas.UnclassifiedChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            document_title=title,
            unit=chunk.unit,
            chapter=chunk.chapter,
            text_preview=(chunk.text or "")[:240],
        )
        for chunk, title in rows
    ]


@router.patch("/chunks/{chunk_id}/topic")
def set_chunk_topic(
    chunk_id: str,
    payload: schemas.ChunkTopicPatch,
    db: DbDep,
    _educator: Annotated[None, RequireEducator],
):
    chunk = db.get(Chunk, chunk_id)
    if chunk is None:
        raise HTTPException(status_code=404, detail=f"Chunk '{chunk_id}' not found.")
    if chunk.subject_id is not None:
        valid = topic_graph_service.read_graph(db, str(chunk.subject_id))
        if payload.topic not in {t["topic"] for t in valid}:
            raise HTTPException(
                status_code=400,
                detail=f"'{payload.topic}' is not a confirmed topic of this subject.",
            )
    chunk.topic = payload.topic
    db.commit()
    return {"chunk_id": chunk_id, "topic": payload.topic}
