"""
backend/services/ingestion_service.py

Orchestrates the full document ingestion pipeline:
  1. Parse  → Extract raw text from uploaded file (PDF/PPTX/DOCX/TXT)
  2. Chunk  → Split text into contextually-enriched chunks
  3. Embed  → Generate 384-dim normalized vectors for each chunk
  4. Store  → Persist chunks + embeddings to the database
  5. Status → Mark document as 'ready' and clean up temp file
  6. Syllabus → Auto-mark previous chapter as 'taught' in ClassContext

Structured print() statements are emitted at every pipeline transition and
in all exception blocks to make debugging trivial during development.
"""

import json
import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from backend.models.db import Chunk, ClassContext, Document, DocumentStatus
from backend.pipeline.chunker import chunk_text
from backend.pipeline.embedder import embed_texts
from backend.pipeline.parser import extract_text

logger = logging.getLogger(__name__)


# ── Main Pipeline Orchestrator ────────────────────────────────────────────────

def process_document(
    db: Session,
    document_id: str,
    file_path: str,
    filename: str,
    embedding_model: Any,
) -> dict:
    """
    Run the full ingestion pipeline for a single uploaded document.

    :param db:              Active SQLAlchemy database session.
    :param document_id:     UUID string of the Document record.
    :param file_path:       Absolute path to the temp file on disk.
    :param filename:        Original filename (used for extension routing).
    :param embedding_model: Pre-loaded SentenceTransformer model instance.
    :return:                Summary dict with chunk_count and status.
    :raises ValueError:     If the Document record is not found in the database.
    """
    print(f"[INGESTION] Starting pipeline for Document ID: {document_id} | File: {filename}")

    # ── Fetch and validate document record ───────────────────────────────────
    doc: Document | None = db.get(Document, document_id)
    if doc is None:
        print(f"[INGESTION ERROR] Document ID '{document_id}' not found in database.")
        raise ValueError(f"Document '{document_id}' not found in database.")

    print(f"[INGESTION] Document record found: title='{doc.title}' | subject='{doc.subject}' "
          f"| unit={doc.unit} | chapter={doc.chapter}")

    # Mark as processing immediately
    doc.status = DocumentStatus.processing
    db.commit()

    chunks_data = []
    try:
        # ── Step 1: Parse ─────────────────────────────────────────────────────
        print(f"[INGESTION STEP 1/5] Parsing file '{filename}'...")
        raw_text = extract_text(file_path=file_path, filename=filename)
        print(f"[INGESTION STEP 1 DONE] Extracted {len(raw_text):,} characters from '{filename}'.")

        # ── Step 2: Chunk ─────────────────────────────────────────────────────
        print(f"[INGESTION STEP 2/5] Chunking extracted text...")
        chunks_data = chunk_text(
            text=raw_text,
            subject=doc.subject or "General",
            unit=doc.unit or 1,
            chapter=doc.chapter or 1,
            chapter_name=doc.chapter_name or "",
            document_title=doc.title,
        )
        print(f"[INGESTION STEP 2 DONE] Produced {len(chunks_data)} text chunks.")

        # ── Step 3: Embed ─────────────────────────────────────────────────────
        print(f"[INGESTION STEP 3/5] Generating embeddings for {len(chunks_data)} chunks...")
        full_texts = [chunk.full_text for chunk in chunks_data]
        embeddings = embed_texts(texts=full_texts, model=embedding_model)
        print(f"[INGESTION STEP 3 DONE] Generated {len(embeddings)} embedding vectors.")

        # ── Step 4: Store chunks ──────────────────────────────────────────────
        print(f"[INGESTION STEP 4/5] Storing {len(chunks_data)} chunks to database...")
        for chunk_data, vector in zip(chunks_data, embeddings):
            chunk = Chunk(
                document_id=document_id,
                text=chunk_data.text,
                contextual_prefix=chunk_data.contextual_prefix,
                full_text=chunk_data.full_text,
                embedding=vector,   # pgvector column — stored as a native vector, not JSON
                subject=doc.subject,
                unit=doc.unit,
                chapter=doc.chapter,
                chunk_index=chunk_data.chunk_index,
                token_count=chunk_data.token_count,
            )
            db.add(chunk)
        print(f"[INGESTION STEP 4 DONE] {len(chunks_data)} Chunk objects added to session.")

        # ── Step 5: Update document status ───────────────────────────────────
        print("[INGESTION STEP 5/5] Updating document status to 'ready'...")
        doc.status = DocumentStatus.ready
        doc.is_indexed = True
        doc.chunk_count = len(chunks_data)

        # ── Step 6: Auto-mark previous chapter as taught ──────────────────────
        _auto_mark_chapter_taught(db, doc)

        # Commit entire transaction atomically
        db.commit()
        print(f"[INGESTION SUCCESS] Pipeline complete for '{filename}'. "
              f"Chunks stored: {len(chunks_data)}")

        return {
            "document_id": document_id,
            "filename": filename,
            "chunk_count": len(chunks_data),
            "status": DocumentStatus.ready.value,
        }

    except Exception as e:
        db.rollback()
        print(f"[INGESTION FAILED] Error processing '{filename}': {str(e)}")
        logger.exception("Ingestion pipeline failed for document '%s'", document_id)

        # Update status to failed in a separate transaction
        try:
            doc.status = DocumentStatus.failed
            db.commit()
            print(f"[INGESTION] Document status set to 'failed' for '{filename}'.")
        except Exception as commit_err:
            print(f"[INGESTION ERROR] Could not update status to failed: {commit_err}")
            db.rollback()

        raise

    finally:
        # ── Cleanup: Remove temp file regardless of outcome ───────────────────
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"[INGESTION CLEANUP] Removed temp file: {file_path}")
            except OSError as cleanup_err:
                print(f"[INGESTION CLEANUP WARNING] Could not remove temp file '{file_path}': {cleanup_err}")
                logger.warning("Failed to remove temp file '%s': %s", file_path, cleanup_err)


# ── Helper: Auto-mark previous chapter as taught ──────────────────────────────

def _auto_mark_chapter_taught(db: Session, doc: Document) -> None:
    """
    When a new chapter document is uploaded, automatically mark the previous
    chapter (chapter - 1) as 'taught' in the associated ClassContext syllabus.

    Skips silently if:
    - ``doc.chapter`` is None or <= 1 (no previous chapter to mark).
    - ``doc.class_id`` is None (no class context configured).
    - No matching ClassContext record exists for this class_id.

    :param db:  Active SQLAlchemy database session.
    :param doc: The Document being ingested.
    """
    if doc.chapter is None or doc.chapter <= 1:
        print("[INGESTION SYLLABUS] No previous chapter to auto-mark (chapter <= 1). Skipping.")
        return

    if not doc.class_id:
        print("[INGESTION SYLLABUS] No class_id set on document. Skipping syllabus update.")
        return

    print(f"[INGESTION SYLLABUS] Looking up ClassContext for class_id='{doc.class_id}'...")
    class_ctx: ClassContext | None = (
        db.query(ClassContext)
        .filter(ClassContext.class_id == doc.class_id)
        .first()
    )

    if class_ctx is None:
        print(f"[INGESTION SYLLABUS] No ClassContext found for class_id='{doc.class_id}'. Skipping.")
        return

    # Parse existing syllabus JSON or start fresh
    try:
        syllabus: dict = json.loads(class_ctx.syllabus_json) if class_ctx.syllabus_json else {}
    except (json.JSONDecodeError, TypeError):
        print("[INGESTION SYLLABUS WARNING] Existing syllabus_json is malformed. Starting fresh.")
        syllabus = {}

    prev_chapter = str(doc.chapter - 1)
    syllabus[prev_chapter] = "taught"
    class_ctx.syllabus_json = json.dumps(syllabus)

    print(f"[INGESTION SYLLABUS] Auto-marked chapter {doc.chapter - 1} as 'taught' "
          f"in class '{doc.class_id}'.")
    logger.info(
        "Auto-marked chapter %d as taught in ClassContext for class_id='%s'",
        doc.chapter - 1,
        doc.class_id,
    )
