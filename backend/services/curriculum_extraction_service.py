from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from backend.models.db import (
    BloomLevel,
    Document,
    DocumentStatus,
    LearningObjective,
    PrerequisiteMap,
    ReviewStatus,
    SyllabusSubtopic,
)
from backend.pipeline.parser import ExtractedDocumentStructure

logger = logging.getLogger(__name__)

# Bloom taxonomy action verbs map
BLOOM_VERB_MAP: dict[str, BloomLevel] = {
    # Remember
    "define": BloomLevel.remember,
    "list": BloomLevel.remember,
    "state": BloomLevel.remember,
    "identify": BloomLevel.remember,
    "recall": BloomLevel.remember,
    "name": BloomLevel.remember,
    "label": BloomLevel.remember,
    "match": BloomLevel.remember,
    # Understand
    "describe": BloomLevel.understand,
    "explain": BloomLevel.understand,
    "summarize": BloomLevel.understand,
    "interpret": BloomLevel.understand,
    "classify": BloomLevel.understand,
    "discuss": BloomLevel.understand,
    "outline": BloomLevel.understand,
    "illustrate": BloomLevel.understand,
    # Apply
    "apply": BloomLevel.apply,
    "solve": BloomLevel.apply,
    "calculate": BloomLevel.apply,
    "demonstrate": BloomLevel.apply,
    "implement": BloomLevel.apply,
    "use": BloomLevel.apply,
    "execute": BloomLevel.apply,
    "compute": BloomLevel.apply,
    # Analyze
    "analyze": BloomLevel.analyze,
    "compare": BloomLevel.analyze,
    "contrast": BloomLevel.analyze,
    "differentiate": BloomLevel.analyze,
    "distinguish": BloomLevel.analyze,
    "examine": BloomLevel.analyze,
    "deconstruct": BloomLevel.analyze,
    # Evaluate
    "evaluate": BloomLevel.evaluate,
    "assess": BloomLevel.evaluate,
    "justify": BloomLevel.evaluate,
    "critique": BloomLevel.evaluate,
    "judge": BloomLevel.evaluate,
    "verify": BloomLevel.evaluate,
    "rate": BloomLevel.evaluate,
    # Create
    "create": BloomLevel.create,
    "design": BloomLevel.create,
    "formulate": BloomLevel.create,
    "build": BloomLevel.create,
    "construct": BloomLevel.create,
    "synthesize": BloomLevel.create,
    "develop": BloomLevel.create,
    "compose": BloomLevel.create,
}


def classify_bloom_level(statement: str) -> str:
    """Classifies a learning objective statement to a Bloom's Taxonomy cognitive level."""
    cleaned = statement.strip().lower()
    words = re.findall(r"\b[a-z]{3,15}\b", cleaned)
    for word in words[:5]:  # Primary action verb typically in first 5 words
        if word in BLOOM_VERB_MAP:
            return BLOOM_VERB_MAP[word].value
    for word in words:
        if word in BLOOM_VERB_MAP:
            return BLOOM_VERB_MAP[word].value
    return BloomLevel.understand.value


def extract_curriculum_hierarchy(
    structure: ExtractedDocumentStructure,
    subject_name: str | None = None,
) -> list[dict[str, Any]]:
    """Extracts a structured hierarchy of Units -> Topics -> Subtopics -> Learning Objectives

    from parsed document pages while preserving page-level provenance.
    """
    candidates: list[dict[str, Any]] = []

    unit_re = re.compile(r"^(?:unit|module|chapter)\s+([0-9ivxlcdm]+)[\s:\-\.]+(.+)$", re.IGNORECASE)
    roman_map = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10}
    lo_re = re.compile(r"^(?:lo|co|objective)\s*([0-9\.\-_]*)\s*[:\-]\s*(.+)$", re.IGNORECASE)

    current_unit_num = 1
    current_topic: dict[str, Any] | None = None

    for page in structure.pages:
        lines = page.text.splitlines()
        for raw_line in lines:
            line = raw_line.strip()
            if not line or len(line) < 3:
                continue

            # 1. Check for Unit/Module Header
            m_unit = unit_re.match(line)
            if m_unit:
                num_str = m_unit.group(1).lower()
                current_unit_num = int(num_str) if num_str.isdigit() else roman_map.get(num_str, current_unit_num + 1)
                unit_title = m_unit.group(2).strip()

                # Start topic from unit title
                current_topic = {
                    "unit": current_unit_num,
                    "topic": unit_title[:500],
                    "description": f"Curriculum unit covering {unit_title}",
                    "source_page_number": page.page_number,
                    "subtopics": [],
                    "learning_objectives": [],
                }
                candidates.append(current_topic)
                continue

            # 2. Check for Learning Objective
            m_lo = lo_re.match(line)
            if m_lo:
                lo_code = f"LO{m_lo.group(1).strip()}" if m_lo.group(1).strip() else None
                lo_stmt = m_lo.group(2).strip()
                bloom = classify_bloom_level(lo_stmt)

                if current_topic is None:
                    current_topic = {
                        "unit": current_unit_num,
                        "topic": (subject_name or "Curriculum") + f" Core Concepts (Unit {current_unit_num})",
                        "description": "General syllabus topics",
                        "source_page_number": page.page_number,
                        "subtopics": [],
                        "learning_objectives": [],
                    }
                    candidates.append(current_topic)

                current_topic["learning_objectives"].append(
                    {
                        "code": lo_code,
                        "statement": lo_stmt,
                        "bloom_level": bloom,
                        "source_page_number": page.page_number,
                    }
                )
                continue

            # 3. Check for Topic / Subtopic items
            # Delimited lists: comma or semicolon separated concepts in syllabus
            if ":" in line and not line.lower().startswith("http"):
                parts = line.split(":", 1)
                topic_lead = parts[0].strip()
                subtopics_str = parts[1].strip()

                if len(topic_lead) > 3 and len(topic_lead) < 120 and len(subtopics_str) > 5:
                    new_topic = {
                        "unit": current_unit_num,
                        "topic": topic_lead[:500],
                        "description": f"Concepts in {topic_lead}",
                        "source_page_number": page.page_number,
                        "subtopics": [],
                        "learning_objectives": [],
                    }
                    # Split comma-separated subtopics
                    for sub in re.split(r"[,;]\s*", subtopics_str):
                        s_clean = sub.strip(" .-")
                        if len(s_clean) >= 3 and len(s_clean) <= 150:
                            new_topic["subtopics"].append(
                                {
                                    "name": s_clean[:255],
                                    "description": f"Subtopic of {topic_lead}",
                                    "source_page_number": page.page_number,
                                }
                            )
                    candidates.append(new_topic)
                    current_topic = new_topic
                    continue

            # Bullet points or numbered items
            if line.startswith(("- ", "* ", "• ")) or re.match(r"^\d+\.\s+", line):
                item_text = re.sub(r"^[-*•\d\.\s]+", "", line).strip()
                if len(item_text) >= 4 and len(item_text) <= 150:
                    if current_topic is not None:
                        current_topic["subtopics"].append(
                            {
                                "name": item_text[:255],
                                "description": f"Subtopic of {current_topic['topic']}",
                                "source_page_number": page.page_number,
                            }
                        )
                    else:
                        current_topic = {
                            "unit": current_unit_num,
                            "topic": item_text[:500],
                            "description": f"Topic: {item_text}",
                            "source_page_number": page.page_number,
                            "subtopics": [],
                            "learning_objectives": [],
                        }
                        candidates.append(current_topic)

    # If no structural elements matched, construct candidate topics from discovered headings
    if not candidates and structure.all_headings:
        for idx, heading in enumerate(structure.all_headings[:15], start=1):
            h_clean = heading.strip()
            if len(h_clean) >= 4:
                candidates.append(
                    {
                        "unit": 1,
                        "topic": h_clean[:500],
                        "description": f"Extracted section topic: {h_clean}",
                        "source_page_number": 1,
                        "subtopics": [],
                        "learning_objectives": [],
                    }
                )

    return candidates


def persist_curriculum_candidates(
    db: Session,
    doc: Document,
    candidates: list[dict[str, Any]],
) -> dict[str, int]:
    """Persists extracted curriculum candidates as draft/pending_review items.

    Reuses existing canonical topics to prevent duplication.
    """
    topics_created = 0
    subtopics_created = 0
    objectives_created = 0

    for cand in candidates:
        topic_name = str(cand.get("topic", "")).strip()
        if not topic_name:
            continue

        unit = cand.get("unit") or doc.unit or 1
        page_num = cand.get("source_page_number", 1)
        desc = cand.get("description")

        # 1. Duplicate check: Reuse existing canonical topic for this subject if present
        topic_row = None
        if doc.subject_id:
            topic_row = (
                db.query(PrerequisiteMap)
                .filter(
                    PrerequisiteMap.subject_id == doc.subject_id,
                    PrerequisiteMap.topic.ilike(topic_name),
                )
                .first()
            )

        if topic_row is None:
            # Create as draft/pending_review topic (NOT CANONICAL YET)
            topic_row = PrerequisiteMap(
                subject=doc.subject,
                subject_id=doc.subject_id,
                unit=unit,
                topic=topic_name[:500],
                description=desc,
                is_canonical=False,
                review_status=ReviewStatus.pending_review.value,
                source_document_id=doc.id,
                source_page_number=page_num,
                created_by=doc.uploaded_by_id,
            )
            db.add(topic_row)
            db.flush()
            topics_created += 1

        # 2. Persist subtopics
        for sub in cand.get("subtopics", []):
            sub_name = str(sub.get("name", "")).strip()
            if not sub_name:
                continue

            existing_sub = (
                db.query(SyllabusSubtopic)
                .filter(
                    SyllabusSubtopic.topic_id == topic_row.id,
                    SyllabusSubtopic.name.ilike(sub_name),
                )
                .first()
            )

            if existing_sub is None:
                sub_row = SyllabusSubtopic(
                    topic_id=topic_row.id,
                    name=sub_name[:255],
                    description=sub.get("description"),
                    order_index=sub.get("order_index", 0),
                    source_document_id=doc.id,
                    source_page_number=sub.get("source_page_number", page_num),
                    review_status=ReviewStatus.pending_review.value,
                )
                db.add(sub_row)
                db.flush()
                subtopics_created += 1

        # 3. Persist learning objectives
        for lo in cand.get("learning_objectives", []):
            lo_stmt = str(lo.get("statement", "")).strip()
            if not lo_stmt:
                continue

            existing_lo = (
                db.query(LearningObjective)
                .filter(
                    LearningObjective.topic_id == topic_row.id,
                    LearningObjective.statement.ilike(lo_stmt),
                )
                .first()
            )

            if existing_lo is None:
                lo_row = LearningObjective(
                    topic_id=topic_row.id,
                    subtopic_id=None,
                    code=lo.get("code"),
                    statement=lo_stmt,
                    bloom_level=lo.get("bloom_level") or BloomLevel.understand.value,
                    source_document_id=doc.id,
                    source_page_number=lo.get("source_page_number", page_num),
                    review_status=ReviewStatus.pending_review.value,
                )
                db.add(lo_row)
                db.flush()
                objectives_created += 1

    db.commit()
    return {
        "topics_created": topics_created,
        "subtopics_created": subtopics_created,
        "objectives_created": objectives_created,
    }


def get_document_curriculum(db: Session, document_id: str | UUID) -> dict[str, Any]:
    """Retrieves all extracted topics, subtopics, and learning objectives linked to a document."""
    doc = db.get(Document, document_id)
    if doc is None:
        raise ValueError(f"Document '{document_id}' not found.")

    topics = (
        db.query(PrerequisiteMap)
        .filter(PrerequisiteMap.source_document_id == doc.id)
        .order_by(PrerequisiteMap.unit.asc().nulls_last(), PrerequisiteMap.order_index.asc())
        .all()
    )

    items = []
    for t in topics:
        subtopics = (
            db.query(SyllabusSubtopic)
            .filter(SyllabusSubtopic.topic_id == t.id)
            .order_by(SyllabusSubtopic.order_index.asc())
            .all()
        )
        objectives = (
            db.query(LearningObjective)
            .filter(LearningObjective.topic_id == t.id)
            .order_by(LearningObjective.order_index.asc())
            .all()
        )

        items.append(
            {
                "id": str(t.id),
                "topic": t.topic,
                "unit": t.unit,
                "description": t.description,
                "is_canonical": t.is_canonical,
                "review_status": t.review_status,
                "source_page_number": t.source_page_number,
                "subtopics": [
                    {
                        "id": str(s.id),
                        "name": s.name,
                        "description": s.description,
                        "review_status": s.review_status,
                        "source_page_number": s.source_page_number,
                    }
                    for s in subtopics
                ],
                "learning_objectives": [
                    {
                        "id": str(o.id),
                        "code": o.code,
                        "statement": o.statement,
                        "bloom_level": o.bloom_level,
                        "review_status": o.review_status,
                        "source_page_number": o.source_page_number,
                    }
                    for o in objectives
                ],
            }
        )

    return {
        "document_id": str(doc.id),
        "document_title": doc.title,
        "document_status": doc.status.value,
        "topics_count": len(items),
        "curriculum": items,
    }


def approve_curriculum(
    db: Session,
    document_id: str | UUID,
    topic_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Faculty review approval: marks topics as canonical and approved, transitions document to ready."""
    doc = db.get(Document, document_id)
    if doc is None:
        raise ValueError(f"Document '{document_id}' not found.")

    query = db.query(PrerequisiteMap).filter(PrerequisiteMap.source_document_id == doc.id)
    if topic_ids:
        query = query.filter(PrerequisiteMap.id.in_([UUID(tid) for tid in topic_ids]))

    approved_topics = query.all()
    approved_count = 0

    for t in approved_topics:
        t.is_canonical = True
        t.review_status = ReviewStatus.approved.value
        approved_count += 1

        # Approve subtopics and learning objectives
        db.query(SyllabusSubtopic).filter(SyllabusSubtopic.topic_id == t.id).update(
            {"review_status": ReviewStatus.approved.value}
        )
        db.query(LearningObjective).filter(LearningObjective.topic_id == t.id).update(
            {"review_status": ReviewStatus.approved.value}
        )

    db.flush()

    # If all items are approved, mark document status as ready
    remaining_pending = (
        db.query(PrerequisiteMap)
        .filter(
            PrerequisiteMap.source_document_id == doc.id,
            PrerequisiteMap.review_status == ReviewStatus.pending_review.value,
        )
        .count()
    )

    if remaining_pending == 0:
        doc.status = DocumentStatus.ready

    db.commit()
    return {
        "document_id": str(doc.id),
        "approved_topics_count": approved_count,
        "remaining_pending": remaining_pending,
        "document_status": doc.status.value,
    }


def reject_curriculum(
    db: Session,
    document_id: str | UUID,
    topic_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Faculty review rejection: marks candidate topics and subtopics as rejected."""
    doc = db.get(Document, document_id)
    if doc is None:
        raise ValueError(f"Document '{document_id}' not found.")

    query = db.query(PrerequisiteMap).filter(PrerequisiteMap.source_document_id == doc.id)
    if topic_ids:
        query = query.filter(PrerequisiteMap.id.in_([UUID(tid) for tid in topic_ids]))

    rejected_topics = query.all()
    rejected_count = 0

    for t in rejected_topics:
        t.is_canonical = False
        t.review_status = ReviewStatus.rejected.value
        rejected_count += 1

        db.query(SyllabusSubtopic).filter(SyllabusSubtopic.topic_id == t.id).update(
            {"review_status": ReviewStatus.rejected.value}
        )
        db.query(LearningObjective).filter(LearningObjective.topic_id == t.id).update(
            {"review_status": ReviewStatus.rejected.value}
        )

    db.commit()
    return {
        "document_id": str(doc.id),
        "rejected_topics_count": rejected_count,
    }
