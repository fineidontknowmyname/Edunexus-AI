import logging
import os
import tempfile
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.api import access
from backend.api.dependencies import CurrentUser, RequireEducator
from backend.core.config import get_settings
from backend.core.database import get_db
from backend.models import schemas
from backend.models.db import Chunk, Class, Document
from backend.pipeline.parser import SUPPORTED_EXTENSIONS, extract_text
from backend.services import misconception_service, subject_service, topic_graph_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["subjects"])
DbDep = Annotated[Session, Depends(get_db)]


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
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
    file: UploadFile = File(...),
):
    access.owned_subject(db, subject_id, current_user)

    filename = os.path.basename(file.filename or "")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{ext}'.")

    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File is larger than the {get_settings().max_upload_mb} MB upload limit.")
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    try:
        tmp.write(content)
        tmp.flush()
        tmp.close()
        syllabus_text = extract_text(file_path=tmp.name, filename=filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:  # noqa: BLE001
        logger.exception("Syllabus parsing failed for %s", filename)
        raise HTTPException(status_code=400, detail="That file couldn't be read. Check it isn't corrupted or password-protected.")
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
    subject = access.existing_subject(db, subject_id)
    return {"subject_id": str(subject.id), "topics": topic_graph_service.read_graph(db, str(subject.id))}


@router.put("/subjects/{subject_id}/topic-graph")
def confirm_topic_graph(
    subject_id: str,
    payload: schemas.TopicGraphConfirm,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    access.owned_subject(db, subject_id, current_user)
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
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    access.owned_subject(db, subject_id, current_user)
    try:
        topic_graph_service.rename_topic(db, subject_id, payload.old_topic, payload.new_topic)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"subject_id": subject_id, "renamed_to": payload.new_topic}


@router.get("/subjects/{subject_id}/unclassified", response_model=list[schemas.UnclassifiedChunk])
def list_unclassified(
    subject_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    subject = access.existing_subject(db, subject_id)
    rows = (
        db.query(Chunk, Document.title)
        .join(Document, Chunk.document_id == Document.id)
        .join(Class, Document.class_id == Class.id)
        .filter(
            Chunk.subject_id == subject.id,
            Chunk.topic.is_(None),
            Document.deleted == False,  # noqa: E712
            Class.educator_id == current_user.id,
        )
        .order_by(Document.title, Chunk.chunk_index)
        .limit(500)
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


@router.get("/subjects/{subject_id}/misconception-rules")
def read_misconception_rules(subject_id: str, db: DbDep, _user: CurrentUser):
    subject_id = str(access.existing_subject(db, subject_id).id)
    rows = misconception_service.list_rules(db, subject_id)
    return {
        "subject_id": subject_id,
        "rules": [
            {
                "topic": r.topic,
                "name": r.name,
                "description": r.description,
                "wrong_answer_keywords": list(r.wrong_answer_keywords or []),
                "question_keywords": list(r.question_keywords or []),
            }
            for r in rows
        ],
    }


@router.post("/subjects/{subject_id}/misconception-rules/draft")
async def draft_misconception_rules(
    subject_id: str, db: DbDep, current_user: CurrentUser, _educator: Annotated[None, RequireEducator]
):
    access.owned_subject(db, subject_id, current_user)
    try:
        rules = await misconception_service.draft_rules_from_topics(db, subject_id)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"Draft failed: {exc}")
    return {"subject_id": subject_id, "rules": rules}


@router.put("/subjects/{subject_id}/misconception-rules")
def confirm_misconception_rules(
    subject_id: str,
    payload: schemas.MisconceptionRulesConfirm,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    access.owned_subject(db, subject_id, current_user)
    try:
        count = misconception_service.replace_rules(
            db, subject_id, [r.model_dump() for r in payload.rules], str(current_user.id)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"subject_id": subject_id, "rule_count": count}


@router.patch("/chunks/{chunk_id}/topic")
def set_chunk_topic(
    chunk_id: str,
    payload: schemas.ChunkTopicPatch,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    chunk = access.owned_chunk(db, chunk_id, current_user)
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
