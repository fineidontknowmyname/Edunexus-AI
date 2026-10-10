import logging
import os
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.api import access
from backend.api.dependencies import CurrentUser, RequireEducator
from backend.core.config import get_settings
from backend.core.database import get_db
from backend.core.rate_limit import rate_limit
from backend.models.db import Document, DocumentFile, DocumentStatus
from backend.services import ingestion_jobs, ingestion_runner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

SUPPORTED_EXTENSIONS = (".pdf", ".pptx", ".docx", ".txt")
READ_CHUNK_BYTES = 1024 * 1024

DbDep = Annotated[Session, Depends(get_db)]
UploadRateLimit = Depends(rate_limit("documents-upload", max_requests=20, window_seconds=600))


def _read_capped(file: UploadFile, max_bytes: int) -> bytes:
    buffer = bytearray()
    while True:
        piece = file.file.read(READ_CHUNK_BYTES)
        if not piece:
            break
        buffer.extend(piece)
        if len(buffer) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"File is larger than the {max_bytes // (1024 * 1024)} MB upload limit.",
            )
    if not buffer:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file is empty.")
    return bytes(buffer)


@router.post("/upload", status_code=202, dependencies=[UploadRateLimit])
def upload_document(
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
    file: UploadFile = File(...),
    class_id: str = Form(...),
    title: str = Form(..., max_length=500),
    subject: str = Form("", max_length=255),
    subject_id: str = Form(""),
    unit: int = Form(1, ge=1, le=100),
    chapter: int = Form(1, ge=1, le=500),
    chapter_name: str = Form("", max_length=500),
):
    class_row = access.owned_class(db, class_id, current_user)

    filename = os.path.basename(file.filename or "")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    content = _read_capped(file, max_bytes)

    resolved_subject_id = class_row.subject_id
    if subject_id:
        resolved_subject_id = access.existing_subject(db, subject_id).id

    doc = Document(
        title=title,
        filename=filename,
        file_path=None,
        subject=subject or class_row.subject or None,
        subject_id=resolved_subject_id,
        unit=unit,
        chapter=chapter,
        chapter_name=chapter_name or None,
        class_id=class_row.id,
        status=DocumentStatus.pending,
        uploaded_by_id=current_user.id,
    )
    db.add(doc)
    db.flush()
    db.add(DocumentFile(document_id=doc.id, data=content, size_bytes=len(content)))
    job = ingestion_jobs.enqueue(db, doc.id)
    db.commit()
    print(f"[API UPLOAD] '{filename}' ({len(content):,} bytes) stored as document {doc.id}, job {job.id}")

    ingestion_runner.notify_new_job()
    return {"document_id": str(doc.id), "job_id": str(job.id), "status": "processing"}


@router.get("/status/{job_id}")
def get_job_status(
    job_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    job = access.owned_job(db, job_id, current_user)
    return ingestion_jobs.status_payload(db, str(job.id))


@router.get("/")
def list_documents(
    class_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    class_row = access.owned_class(db, class_id, current_user)
    docs = (
        db.query(Document)
        .filter(Document.class_id == class_row.id, Document.deleted == False)  # noqa: E712
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
def delete_document(
    document_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    doc = access.owned_document(db, document_id, current_user)
    doc.deleted = True
    db.commit()
    return {"message": "Document deleted."}
