import logging
import os
import tempfile
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from backend.api import access
from backend.api.dependencies import CurrentUser, RequireEducator
from backend.core.config import get_settings
from backend.core.database import get_db
from backend.core.rate_limit import rate_limit
from backend.models import schemas
from backend.models.db import (
    Document,
    DocumentFile,
    DocumentStatus,
    LearningObjective,
    PrerequisiteMap,
    SyllabusSubtopic,
)
from backend.pipeline.parser import (
    IMAGE_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    extract_multi_image_structure,
    validate_document_content,
)
from backend.services import curriculum_extraction_service, ingestion_jobs, ingestion_runner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])
READ_CHUNK_BYTES = 1024 * 1024

DbDep = Annotated[Session, Depends(get_db)]
UploadRateLimit = Depends(rate_limit("documents-upload", max_requests=30, window_seconds=600))


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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file is empty (0 bytes).")
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

    filename = os.path.basename(file.filename or "upload")
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    content = _read_capped(file, max_bytes)

    # Deep content, extension, and magic bytes verification
    try:
        ext, mime_type, file_size, sha256_hash = validate_document_content(content, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Duplicate detection: Check if an identical document already exists in this class
    existing_doc = (
        db.query(Document)
        .filter(
            Document.class_id == class_row.id,
            Document.file_hash_sha256 == sha256_hash,
            Document.deleted == False,  # noqa: E712
        )
        .first()
    )
    if existing_doc:
        return {
            "document_id": str(existing_doc.id),
            "status": existing_doc.status.value,
            "duplicate": True,
            "message": "An identical document has already been uploaded for this class.",
            "filename": existing_doc.filename,
        }

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
        file_hash_sha256=sha256_hash,
        mime_type=mime_type,
        file_size_bytes=file_size,
    )
    db.add(doc)
    db.flush()

    # Original Document Preservation: Store raw bytes in DocumentFile (never deleted)
    db.add(DocumentFile(document_id=doc.id, data=content, size_bytes=file_size))
    job = ingestion_jobs.enqueue(db, doc.id)
    db.commit()

    print(f"[API UPLOAD] '{filename}' ({file_size:,} bytes, sha256={sha256_hash[:8]}) preserved as doc {doc.id}, job {job.id}")
    ingestion_runner.notify_new_job()
    return {
        "document_id": str(doc.id),
        "job_id": str(job.id),
        "status": "processing",
        "file_hash_sha256": sha256_hash,
        "mime_type": mime_type,
        "file_size_bytes": file_size,
    }


@router.post("/syllabus-upload", status_code=202, dependencies=[UploadRateLimit])
async def upload_syllabus_documents(
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
    class_id: str = Form(...),
    title: str = Form("Syllabus Notes", max_length=500),
    files: list[UploadFile] = File(...),
    subject_id: str = Form(""),
):
    """Supports single or multi-image/multi-file uploads for syllabi and lecture note sets.

    Preserves original documents and triggers structural curriculum extraction.
    """
    class_row = access.owned_class(db, class_id, current_user)
    if not files:
        raise HTTPException(status_code=400, detail="No files provided for syllabus upload.")

    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    resolved_subject_id = class_row.subject_id
    if subject_id:
        resolved_subject_id = access.existing_subject(db, subject_id).id

    # If multiple images were uploaded, process them as a multi-page syllabus
    is_all_images = all(os.path.splitext(f.filename or "")[1].lower() in IMAGE_EXTENSIONS for f in files)

    if len(files) > 1 and is_all_images:
        image_tuples: list[tuple[str, str]] = []
        raw_contents: list[bytes] = []
        temp_paths: list[str] = []

        try:
            for idx, f in enumerate(files):
                clean_name = os.path.basename(f.filename or f"scan_page_{idx + 1}.jpg")
                content = _read_capped(f, max_bytes)
                raw_contents.append(content)
                ext, _, _, _ = validate_document_content(content, clean_name)

                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
                tmp.write(content)
                tmp.flush()
                tmp.close()
                temp_paths.append(tmp.name)
                image_tuples.append((tmp.name, clean_name))

            doc_structure = extract_multi_image_structure(image_tuples)

            doc = Document(
                title=title,
                filename=f"scanned_syllabus_{len(files)}_pages.jpg",
                file_path=None,
                subject=class_row.subject or None,
                subject_id=resolved_subject_id,
                unit=1,
                chapter=1,
                class_id=class_row.id,
                status=DocumentStatus.processing,
                uploaded_by_id=current_user.id,
                file_hash_sha256=doc_structure.sha256_hash,
                mime_type="image/jpeg",
                file_size_bytes=doc_structure.file_size_bytes,
            )
            db.add(doc)
            db.flush()

            # Preserve composite/first page in DocumentFile
            db.add(DocumentFile(document_id=doc.id, data=raw_contents[0], size_bytes=len(raw_contents[0])))

            # Extract and persist curriculum hierarchy candidates
            candidates = curriculum_extraction_service.extract_curriculum_hierarchy(
                doc_structure, subject_name=class_row.subject
            )
            curriculum_stats = {}
            if candidates and resolved_subject_id:
                curriculum_stats = curriculum_extraction_service.persist_curriculum_candidates(
                    db, doc, candidates
                )
                doc.status = DocumentStatus.review_required
            else:
                doc.status = DocumentStatus.ready

            doc.processing_metadata = {
                "multi_page_scan": True,
                "pages_uploaded": len(files),
                "curriculum_extracted": curriculum_stats,
            }
            db.commit()

            return {
                "document_id": str(doc.id),
                "status": doc.status.value,
                "pages_processed": len(files),
                "curriculum_candidates": curriculum_stats,
            }

        finally:
            for p in temp_paths:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
    else:
        # Standard upload loop for individual documents
        uploaded_docs = []
        for f in files:
            clean_name = os.path.basename(f.filename or "upload")
            content = _read_capped(f, max_bytes)
            ext, mime_type, file_size, sha256_hash = validate_document_content(content, clean_name)

            doc = Document(
                title=f"{title} - {clean_name}",
                filename=clean_name,
                subject=class_row.subject or None,
                subject_id=resolved_subject_id,
                unit=1,
                chapter=1,
                class_id=class_row.id,
                status=DocumentStatus.pending,
                uploaded_by_id=current_user.id,
                file_hash_sha256=sha256_hash,
                mime_type=mime_type,
                file_size_bytes=file_size,
            )
            db.add(doc)
            db.flush()
            db.add(DocumentFile(document_id=doc.id, data=content, size_bytes=file_size))
            job = ingestion_jobs.enqueue(db, doc.id)
            uploaded_docs.append({"document_id": str(doc.id), "filename": clean_name, "job_id": str(job.id)})

        db.commit()
        ingestion_runner.notify_new_job()
        return {"uploaded_count": len(uploaded_docs), "documents": uploaded_docs}


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
            "file_hash_sha256": doc.file_hash_sha256,
            "mime_type": doc.mime_type,
            "file_size_bytes": doc.file_size_bytes,
            "error_message": doc.error_message,
            "processing_metadata": doc.processing_metadata or {},
            "created_at": doc.created_at.isoformat(),
        }
        for doc in docs
    ]


@router.get("/{document_id}/file")
def get_original_file(
    document_id: str,
    db: DbDep,
    current_user: CurrentUser,
):
    """Retrieves the preserved original source document bytes for authorized educators and enrolled students."""
    doc = access.accessible_document(db, document_id, current_user)
    file_row = db.query(DocumentFile).filter(DocumentFile.document_id == doc.id).first()
    if file_row is None:
        raise HTTPException(status_code=404, detail="Original document binary is not found.")

    return Response(
        content=file_row.data,
        media_type=doc.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'inline; filename="{doc.filename}"',
            "X-SHA256-Checksum": doc.file_hash_sha256 or "",
        },
    )


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


# --- CURRICULUM REVIEW & APPROVAL ENDPOINTS ---


@router.get("/{document_id}/curriculum")
def get_extracted_curriculum(
    document_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    """Retrieves AI-extracted Units -> Topics -> Subtopics -> Objectives awaiting review."""
    access.owned_document(db, document_id, current_user)
    try:
        return curriculum_extraction_service.get_document_curriculum(db, document_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{document_id}/curriculum/approve")
def approve_curriculum(
    document_id: str,
    payload: schemas.CurriculumReviewApprovePayload,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    """Faculty reviews and approves extracted curriculum items into canonical topics."""
    access.owned_document(db, document_id, current_user)
    try:
        return curriculum_extraction_service.approve_curriculum(
            db, document_id, topic_ids=payload.topic_ids
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{document_id}/curriculum/reject")
def reject_curriculum(
    document_id: str,
    payload: schemas.CurriculumReviewRejectPayload,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    """Faculty rejects extracted curriculum items."""
    access.owned_document(db, document_id, current_user)
    try:
        return curriculum_extraction_service.reject_curriculum(
            db, document_id, topic_ids=payload.topic_ids
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/curriculum/topics/{topic_id}")
def update_curriculum_topic(
    topic_id: str,
    payload: schemas.TopicUpdatePayload,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    """Faculty edits an extracted topic candidate."""
    topic = db.get(PrerequisiteMap, UUID(topic_id))
    if topic is None:
        raise HTTPException(status_code=404, detail="Curriculum topic not found.")

    if payload.topic is not None:
        topic.topic = payload.topic[:500]
    if payload.unit is not None:
        topic.unit = payload.unit
    if payload.description is not None:
        topic.description = payload.description

    db.commit()
    return {"id": str(topic.id), "topic": topic.topic, "unit": topic.unit}


@router.put("/curriculum/subtopics/{subtopic_id}")
def update_curriculum_subtopic(
    subtopic_id: str,
    payload: schemas.SubtopicUpdatePayload,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    """Faculty edits an extracted subtopic candidate."""
    subtopic = db.get(SyllabusSubtopic, UUID(subtopic_id))
    if subtopic is None:
        raise HTTPException(status_code=404, detail="Curriculum subtopic not found.")

    if payload.name is not None:
        subtopic.name = payload.name[:255]
    if payload.description is not None:
        subtopic.description = payload.description

    db.commit()
    return {"id": str(subtopic.id), "name": subtopic.name}


@router.put("/curriculum/objectives/{objective_id}")
def update_curriculum_objective(
    objective_id: str,
    payload: schemas.ObjectiveUpdatePayload,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    """Faculty edits an extracted learning objective candidate."""
    obj = db.get(LearningObjective, UUID(objective_id))
    if obj is None:
        raise HTTPException(status_code=404, detail="Learning objective not found.")

    if payload.statement is not None:
        obj.statement = payload.statement
    if payload.code is not None:
        obj.code = payload.code[:50]
    if payload.bloom_level is not None:
        obj.bloom_level = payload.bloom_level[:50]

    db.commit()
    return {"id": str(obj.id), "statement": obj.statement, "bloom_level": obj.bloom_level}
