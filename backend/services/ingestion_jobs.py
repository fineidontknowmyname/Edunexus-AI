from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.models.db import IngestionJob, IngestionJobStatus

logger = logging.getLogger(__name__)

STALE_AFTER_SECONDS = 15 * 60
MAX_ATTEMPTS = 3


def enqueue(db: Session, document_id: str) -> IngestionJob:
    job = IngestionJob(document_id=document_id, status=IngestionJobStatus.queued)
    db.add(job)
    db.commit()
    db.refresh(job)
    print(f"[INGESTION QUEUE] Enqueued job {job.id} for document {document_id}")
    return job


def claim_next(db: Session) -> IngestionJob | None:
    row = db.execute(
        text(
            """
            SELECT id FROM ingestion_jobs
            WHERE status = 'queued'
            ORDER BY created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """
        )
    ).first()
    if row is None:
        return None

    job = db.get(IngestionJob, row[0])
    job.status = IngestionJobStatus.processing
    job.attempts += 1
    job.claimed_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    print(f"[INGESTION QUEUE] Claimed job {job.id} (attempt {job.attempts})")
    return job


def mark(
    db: Session,
    job_id: str,
    status: IngestionJobStatus,
    *,
    error: str | None = None,
    chunk_count: int | None = None,
) -> None:
    job = db.get(IngestionJob, job_id)
    if job is None:
        return
    job.status = status
    if error is not None:
        job.error = error[:2000]
    if chunk_count is not None:
        job.chunk_count = chunk_count
    db.commit()
    print(f"[INGESTION QUEUE] Job {job_id} -> {status.value}")


def requeue(db: Session, job_id: str, error: str | None = None) -> None:
    job = db.get(IngestionJob, job_id)
    if job is None:
        return
    if job.attempts >= MAX_ATTEMPTS:
        job.status = IngestionJobStatus.failed
        job.error = (error or "max attempts exceeded")[:2000]
        print(f"[INGESTION QUEUE] Job {job_id} failed permanently after {job.attempts} attempts")
    else:
        job.status = IngestionJobStatus.queued
        job.claimed_at = None
        job.error = (error or "")[:2000]
        print(f"[INGESTION QUEUE] Job {job_id} re-queued (attempt {job.attempts})")
    db.commit()


def sweep_stale(db: Session) -> int:
    cutoff = datetime.utcnow() - timedelta(seconds=STALE_AFTER_SECONDS)
    stale = (
        db.query(IngestionJob)
        .filter(
            IngestionJob.status == IngestionJobStatus.processing,
            IngestionJob.claimed_at < cutoff,
        )
        .all()
    )
    for job in stale:
        requeue(db, str(job.id), error="reclaimed after stale timeout")
    if stale:
        print(f"[INGESTION QUEUE] Swept {len(stale)} stale job(s) back to the queue")
    return len(stale)


def drain_once(session_factory, embedding_model: Any) -> bool:
    from backend.services.ingestion_service import process_job

    db: Session = session_factory()
    try:
        job = claim_next(db)
        if job is None:
            return False
        job_id = str(job.id)
        document_id = str(job.document_id)
    finally:
        db.close()

    work_db: Session = session_factory()
    try:
        result = process_job(work_db, document_id=document_id, embedding_model=embedding_model)
        mark(work_db, job_id, IngestionJobStatus.done, chunk_count=result.get("chunk_count"))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ingestion job %s failed", job_id)
        requeue(work_db, job_id, error=str(exc))
    finally:
        work_db.close()
    return True


def status_payload(db: Session, job_id: str) -> dict | None:
    job = db.get(IngestionJob, job_id)
    if job is None:
        return None
    external = {
        IngestionJobStatus.queued: "processing",
        IngestionJobStatus.processing: "processing",
        IngestionJobStatus.done: "ready",
        IngestionJobStatus.failed: "failed",
    }[job.status]
    return {
        "document_id": str(job.document_id),
        "status": external,
        "chunk_count": job.chunk_count or 0,
        "detail": job.error,
    }
