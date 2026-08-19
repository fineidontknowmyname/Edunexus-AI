import os
import tempfile
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.api.dependencies import CurrentUser, RequireEducator
from backend.core.database import get_db
from backend.models.db import Class, Document, DocumentStatus
from backend.services.ingestion_service import process_document

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

job_status: dict[str, dict] = {}

SUPPORTED_EXTENSIONS = (".pdf", ".pptx", ".docx", ".txt")

DbDep = Annotated[Session, Depends(get_db)]


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
    unit: int = Form(1),
    chapter: int = Form(1),
    chapter_name: str = Form(""),
):
    print(f"[API UPLOAD] Received file '{file.filename}' for Class ID: {class_id} "
          f"| Title: '{title}' | Subject: '{subject}' | Unit: {unit} | Chapter: {chapter}")

    class_row = db.get(Class, class_id)
    if class_row is None:
        print(f"[API UPLOAD ERROR] Class ID '{class_id}' does not exist.")
        raise HTTPException(
            status_code=404,
            detail=f"Class '{class_id}' not found. Create it via POST /classes/ first.",
        )

    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        print(f"[API UPLOAD ERROR] Rejected unsupported file extension '{ext}' for file '{filename}'")
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    try:
        suffix = ext
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        content = file.file.read()
        tmp.write(content)
        tmp.flush()
        tmp.close()
        file_path = tmp.name
        print(f"[API UPLOAD] Saved '{filename}' to temp path: {file_path} ({len(content):,} bytes)")
    except Exception as e:
        print(f"[API UPLOAD ERROR] Failed to save uploaded file: {e}")
        logger.exception("Failed to write uploaded file to temp path")
        raise HTTPException(status_code=500, detail="Failed to store uploaded file.")

    doc = Document(
        title=title,
        filename=filename,
        file_path=file_path,
        subject=subject or None,
        unit=unit,
        chapter=chapter,
        chapter_name=chapter_name or None,
        class_id=class_id,
        status=DocumentStatus.processing,
        uploaded_by_id=current_user.id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    document_id = str(doc.id)

    print(f"[API UPLOAD] Document record created: ID={document_id}")

    job_id = str(uuid.uuid4())
    job_status[job_id] = {
        "document_id": document_id,
        "status": "processing",
        "detail": None,
    }

    def run_ingestion() -> None:
        print(f"[BACKGROUND TASK] Dispatching ingestion for Job ID: {job_id} | Document: {document_id}")
        from backend.core.database import SessionLocal

        ingestion_db = SessionLocal()
        try:
            from backend.main import app
            embedding_model = getattr(app.state, "embedding_model", None)
            if embedding_model is None:
                raise RuntimeError("Embedding model not loaded in app.state. Check startup lifespan.")

            result = process_document(
                db=ingestion_db,
                document_id=document_id,
                file_path=file_path,
                filename=filename,
                embedding_model=embedding_model,
            )
            job_status[job_id]["status"] = "ready"
            job_status[job_id]["chunk_count"] = result.get("chunk_count", 0)
            print(f"[BACKGROUND TASK SUCCESS] Job {job_id} completed. "
                  f"Chunks: {result.get('chunk_count', 0)}")
        except Exception as e:
            job_status[job_id]["status"] = "failed"
            job_status[job_id]["detail"] = str(e)
            print(f"[BACKGROUND TASK FAILED] Job {job_id} failed: {e}")
            logger.exception("Background ingestion job %s failed", job_id)
        finally:
            ingestion_db.close()

    background_tasks.add_task(run_ingestion)
    print(f"[API UPLOAD] Ingestion job queued. Job ID: {job_id}")

    return {
        "document_id": document_id,
        "job_id": job_id,
        "status": "processing",
    }


@router.get("/status/{job_id}")
def get_job_status(job_id: str, _educator: Annotated[None, RequireEducator]):
    print(f"[API POLL] Status requested for Job ID: {job_id}")

    if job_id not in job_status:
        print(f"[API POLL ERROR] Job ID '{job_id}' not found in job registry.")
        raise HTTPException(
            status_code=404,
            detail=f"Job ID '{job_id}' not found. It may have expired or never existed.",
        )

    result = job_status[job_id]
    print(f"[API POLL] Job {job_id} -> status='{result['status']}'")
    return result


@router.get("/")
def list_documents(
    class_id: str,
    db: DbDep,
    _educator: Annotated[None, RequireEducator],
):
    print(f"[API LIST] Listing documents for class_id='{class_id}'")
    docs = (
        db.query(Document)
        .filter(Document.class_id == class_id, Document.deleted == False)  # noqa: E712
        .order_by(Document.created_at.desc())
        .all()
    )
    print(f"[API LIST] Found {len(docs)} document(s) for class_id='{class_id}'")
    return [
        {
            "id": str(doc.id),
            "title": doc.title,
            "filename": doc.filename,
            "subject": doc.subject,
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
    _educator: Annotated[None, RequireEducator],
):
    print(f"[API DELETE] Soft-delete requested for Document ID: {document_id}")

    doc = db.get(Document, document_id)
    if doc is None or doc.deleted:
        print(f"[API DELETE ERROR] Document '{document_id}' not found or already deleted.")
        raise HTTPException(
            status_code=404,
            detail=f"Document '{document_id}' not found.",
        )

    doc.deleted = True
    db.commit()
    print(f"[API DELETE SUCCESS] Document '{document_id}' soft-deleted.")
    return {"message": f"Document '{document_id}' deleted successfully."}
