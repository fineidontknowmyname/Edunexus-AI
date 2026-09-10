import logging
import os
import tempfile
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.api.dependencies import CurrentUser, RequireEducator
from backend.core.database import SessionLocal, get_db
from backend.models.db import Class, Document, DocumentStatus
from backend.services import ingestion_jobs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

SUPPORTED_EXTENSIONS = (".pdf", ".pptx", ".docx", ".txt")

DbDep = Annotated[Session, Depends(get_db)]


def _drain_in_background() -> None:
    from backend.main import app

    embedding_model = getattr(app.state, "embedding_model", None)
    if embedding_model is None:
        logger.error("Embedding model not loaded; cannot drain ingestion queue.")
        return
    while ingestion_jobs.drain_once(SessionLocal, embedding_model):
        pass


@router.post("/upload", status_code=202)
def upload_document(
    background_tasks: BackgroundTasks,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
    file: UploadFile = File(...),
    class_id: str = Form(...),
    title: str = Form(...),
    subject: str = Form(""),
    subject_id: str = Form(""),
    unit: int = Form(1),
    chapter: int = Form(1),
    chapter_name: str = Form(""),
):
    print(f"[API UPLOAD] '{file.filename}' class={class_id} subject_id={subject_id!r} subject={subject!r}")

    class_row = db.get(Class, class_id)
    if class_row is None:
        raise HTTPException(status_code=404, detail=f"Class '{class_id}' not found.")

    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        content = file.file.read()
        tmp.write(content)
        tmp.flush()
        tmp.close()
        file_path = tmp.name
        print(f"[API UPLOAD] Saved to temp: {file_path} ({len(content):,} bytes)")
    except Exception:
        logger.exception("Failed to write uploaded file to temp path")
        raise HTTPException(status_code=500, detail="Failed to store uploaded file.")

    resolved_subject_id = subject_id or class_row.subject_id or None

    doc = Document(
        title=title,
        filename=filename,
        file_path=file_path,
        subject=subject or class_row.subject or None,
        subject_id=resolved_subject_id,
        unit=unit,
        chapter=chapter,
        chapter_name=chapter_name or None,
        class_id=class_id,
        status=DocumentStatus.pending,
        uploaded_by_id=current_user.id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    document_id = str(doc.id)

    job = ingestion_jobs.enqueue(db, document_id)
    background_tasks.add_task(_drain_in_background)
    print(f"[API UPLOAD] Document {document_id} queued as job {job.id}")

    return {"document_id": document_id, "job_id": str(job.id), "status": "processing"}


@router.get("/status/{job_id}")
def get_job_status(job_id: str, db: DbDep, _educator: Annotated[None, RequireEducator]):
    payload = ingestion_jobs.status_payload(db, job_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return payload


@router.get("/")
def list_documents(class_id: str, db: DbDep, _educator: Annotated[None, RequireEducator]):
    docs = (
        db.query(Document)
        .filter(Document.class_id == class_id, Document.deleted == False)  # noqa: E712
        .order_by(Document.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(doc.id),
            "title": doc.title,
            "filename": doc.filename,
            "subject": doc.subject,
            "subject_id": str(doc.subject_id) if doc.subject_id else None,
            "unit": doc.unit,
            "chapter": doc.chapter,
            "chapter_name": doc.chapter_name,
            "status": doc.status.value,
            "chunk_count": doc.chunk_count,
            "created_at": doc.created_at.isoformat(),
        }
        for doc in docs
    ]


@router.delete("/{document_id}", status_code=200)
def delete_document(document_id: str, db: DbDep, _educator: Annotated[None, RequireEducator]):
    doc = db.get(Document, document_id)
    if doc is None or doc.deleted:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")
    doc.deleted = True
    db.commit()
    return {"message": f"Document '{document_id}' deleted successfully."}
