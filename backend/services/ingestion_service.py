import json
import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from backend.models.db import Chunk, Class, ClassContext, Document, DocumentStatus
from backend.pipeline.chunker import chunk_text
from backend.pipeline.embedder import embed_texts
from backend.pipeline.parser import extract_text
from backend.services import classification_service, topic_graph_service

logger = logging.getLogger(__name__)


def _resolve_subject(db: Session, doc: Document) -> tuple[Any, str | None]:
    subject_id = doc.subject_id
    subject_name = doc.subject

    if subject_id is None and doc.class_id:
        class_row = db.get(Class, doc.class_id)
        if class_row is not None:
            subject_id = class_row.subject_id
            subject_name = subject_name or class_row.subject

    if subject_id is not None:
        from backend.models.db import Subject

        subject_row = db.get(Subject, subject_id)
        if subject_row is not None:
            subject_name = subject_row.name
    return subject_id, subject_name


def process_job(db: Session, document_id: str, embedding_model: Any) -> dict:
    print(f"[INGESTION] Starting pipeline for Document ID: {document_id}")

    doc: Document | None = db.get(Document, document_id)
    if doc is None:
        raise ValueError(f"Document '{document_id}' not found in database.")

    file_path = doc.file_path
    filename = doc.filename
    doc.status = DocumentStatus.processing
    db.commit()

    subject_id, subject_name = _resolve_subject(db, doc)
    print(
        f"[INGESTION] Document '{doc.title}' | subject_id={subject_id} subject='{subject_name}' "
        f"class_id={doc.class_id} unit={doc.unit} chapter={doc.chapter}"
    )

    try:
        print(f"[INGESTION STEP 1/6] Parsing '{filename}'...")
        raw_text = extract_text(file_path=file_path, filename=filename)
        print(f"[INGESTION STEP 1 DONE] Extracted {len(raw_text):,} characters.")

        print("[INGESTION STEP 2/6] Chunking...")
        chunks_data = chunk_text(
            text=raw_text,
            subject=subject_name or "General",
            unit=doc.unit or 1,
            chapter=doc.chapter or 1,
            chapter_name=doc.chapter_name or "",
            document_title=doc.title,
        )
        print(f"[INGESTION STEP 2 DONE] {len(chunks_data)} chunks.")

        print(f"[INGESTION STEP 3/6] Embedding {len(chunks_data)} chunks...")
        full_texts = [c.full_text for c in chunks_data]
        embeddings = embed_texts(texts=full_texts, model=embedding_model)
        print(f"[INGESTION STEP 3 DONE] {len(embeddings)} vectors.")

        print("[INGESTION STEP 4/6] Assigning topics...")
        topic_by_index = _classify(db, subject_id, chunks_data, embeddings, doc, embedding_model)
        assigned = sum(1 for v in topic_by_index.values() if v)
        print(f"[INGESTION STEP 4 DONE] {assigned}/{len(chunks_data)} chunks tagged to a topic.")

        print(f"[INGESTION STEP 5/6] Storing {len(chunks_data)} chunks...")
        for i, (chunk_data, vector) in enumerate(zip(chunks_data, embeddings)):
            db.add(
                Chunk(
                    document_id=document_id,
                    class_id=doc.class_id,
                    subject_id=subject_id,
                    topic=topic_by_index.get(i),
                    text=chunk_data.text,
                    contextual_prefix=chunk_data.contextual_prefix,
                    full_text=chunk_data.full_text,
                    embedding=vector,
                    subject=subject_name,
                    unit=doc.unit,
                    chapter=doc.chapter,
                    chunk_index=chunk_data.chunk_index,
                    token_count=chunk_data.token_count,
                )
            )

        print("[INGESTION STEP 6/6] Finalising...")
        doc.status = DocumentStatus.ready
        doc.is_indexed = True
        doc.chunk_count = len(chunks_data)

        _auto_mark_chapter_taught(db, doc)
        _auto_mark_topics_taught(db, doc, [t for t in topic_by_index.values() if t])

        db.commit()
        print(f"[INGESTION SUCCESS] '{filename}' -> {len(chunks_data)} chunks stored.")
        return {
            "document_id": document_id,
            "filename": filename,
            "chunk_count": len(chunks_data),
            "status": DocumentStatus.ready.value,
        }

    except Exception as e:
        db.rollback()
        print(f"[INGESTION FAILED] '{filename}': {e}")
        logger.exception("Ingestion pipeline failed for document '%s'", document_id)
        try:
            doc.status = DocumentStatus.failed
            db.commit()
        except Exception as commit_err:
            print(f"[INGESTION ERROR] Could not set failed status: {commit_err}")
            db.rollback()
        raise

    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"[INGESTION CLEANUP] Removed temp file: {file_path}")
            except OSError as cleanup_err:
                logger.warning("Failed to remove temp file '%s': %s", file_path, cleanup_err)


def _classify(
    db: Session,
    subject_id: Any,
    chunks_data: list,
    embeddings: list[list[float]],
    doc: Document,
    embedding_model: Any,
) -> dict[int, str | None]:
    if subject_id is None:
        return {i: None for i in range(len(chunks_data))}

    names, anchor_vectors = topic_graph_service.topic_anchors(db, subject_id, embedding_model)
    if not names:
        print("[INGESTION] Subject has no confirmed Topic Graph yet — chunks left unclassified.")
        return {i: None for i in range(len(chunks_data))}

    meta = [
        {"unit": doc.unit, "chapter": doc.chapter, "chapter_name": doc.chapter_name or ""}
        for _ in chunks_data
    ]
    return classification_service.assign_topics(meta, embeddings, names, anchor_vectors)


def _auto_mark_chapter_taught(db: Session, doc: Document) -> None:
    if doc.chapter is None or doc.chapter <= 1 or not doc.class_id:
        return
    class_ctx = _class_context(db, doc.class_id)
    if class_ctx is None:
        return
    syllabus = _load_syllabus(class_ctx)
    syllabus[str(doc.chapter - 1)] = "taught"
    class_ctx.syllabus_json = json.dumps(syllabus)
    print(f"[INGESTION SYLLABUS] Auto-marked chapter {doc.chapter - 1} taught in class '{doc.class_id}'.")


def _auto_mark_topics_taught(db: Session, doc: Document, topics: list[str]) -> None:
    if not topics or not doc.class_id:
        return
    class_ctx = _class_context(db, doc.class_id)
    if class_ctx is None:
        return
    syllabus = _load_syllabus(class_ctx)
    for topic in set(topics):
        syllabus[topic] = "taught"
    class_ctx.syllabus_json = json.dumps(syllabus)
    print(f"[INGESTION SYLLABUS] Auto-marked {len(set(topics))} topic(s) taught in class '{doc.class_id}'.")


def _class_context(db: Session, class_id: str) -> ClassContext | None:
    return db.query(ClassContext).filter(ClassContext.class_id == class_id).first()


def _load_syllabus(class_ctx: ClassContext) -> dict:
    try:
        return json.loads(class_ctx.syllabus_json) if class_ctx.syllabus_json else {}
    except (json.JSONDecodeError, TypeError):
        return {}
