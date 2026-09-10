import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from backend.core.prerequisites import get_prerequisites, load_prerequisite_map
from backend.models.db import (
    Class,
    ClassContext,
    EducatorNote,
    Engagement,
    InteractionPattern,
    Misconception,
    TopicMastery,
)


def assemble_class_context(db: Session, class_id: str) -> dict[str, Any]:
    print(f"[CONTEXT] Assembling class context for class_id={class_id}")
    class_row = db.get(Class, class_id)
    if class_row is None:
        print(f"[CONTEXT ERROR] Class '{class_id}' not found.")
        raise ValueError(f"Class '{class_id}' not found.")

    ctx = db.query(ClassContext).filter(ClassContext.class_id == class_id).first()
    syllabus = json.loads(ctx.syllabus_json) if ctx and ctx.syllabus_json else {}
    assessments = json.loads(ctx.assessments_json) if ctx and ctx.assessments_json else []

    print(
        f"[CONTEXT] Class context assembled: subject={class_row.subject} "
        f"subject_id={class_row.subject_id} syllabus_entries={len(syllabus)} assessments={len(assessments)}"
    )

    return {
        "class_id": str(class_id),
        "subject": class_row.subject,
        "subject_id": str(class_row.subject_id) if class_row.subject_id else None,
        "syllabus": syllabus,
        "assessments": assessments,
        "teacher_emphasis": ctx.teacher_emphasis if ctx else None,
    }


def assemble_student_context(db: Session, student_id: str, class_id: str) -> dict[str, Any]:
    print(f"[CONTEXT] Assembling student context: student={student_id} class={class_id}")

    masteries = (
        db.query(TopicMastery)
        .filter(TopicMastery.student_id == student_id, TopicMastery.class_id == class_id)
        .all()
    )
    mastery = {
        m.topic: {"score": m.mastery_score, "attempts": m.attempt_count, "trend": m.trend.value}
        for m in masteries
    }
    weak_topics = [m.topic for m in masteries if m.attempt_count > 0 and m.mastery_score < 0.60]
    strong_topics = [m.topic for m in masteries if m.mastery_score >= 0.80]

    misconception_rows = (
        db.query(Misconception)
        .filter(
            Misconception.student_id == student_id,
            Misconception.class_id == class_id,
            Misconception.resolved == False,  # noqa: E712
        )
        .order_by(Misconception.detected_at.desc())
        .all()
    )
    misconceptions = [{"topic": m.topic, "description": m.description} for m in misconception_rows]

    pattern_rows = db.query(InteractionPattern).filter(InteractionPattern.student_id == student_id).all()
    interaction_patterns = {
        p.topic: {
            "questions_asked": p.questions_asked,
            "last_asked": p.last_asked_at.isoformat() if p.last_asked_at else None,
        }
        for p in pattern_rows
    }

    engagement_row = db.query(Engagement).filter(Engagement.student_id == student_id).first()
    engagement = {
        "current_streak": engagement_row.current_streak if engagement_row else 0,
        "last_interaction": (
            engagement_row.last_interaction_date.isoformat()
            if engagement_row and engagement_row.last_interaction_date
            else None
        ),
        "staleness_flag": engagement_row.staleness_flag if engagement_row else False,
    }

    class_context = assemble_class_context(db, class_id)
    upcoming_focus = _compute_upcoming_focus(class_context["assessments"], weak_topics)

    latest_note_row = (
        db.query(EducatorNote)
        .filter(EducatorNote.student_id == student_id, EducatorNote.class_id == class_id)
        .order_by(EducatorNote.created_at.desc())
        .first()
    )
    latest_educator_note = latest_note_row.note if latest_note_row else None

    print(
        f"[CONTEXT] Student context: {len(mastery)} topics tracked | "
        f"weak={weak_topics} strong={strong_topics} | "
        f"misconceptions={len(misconceptions)} | staleness={engagement['staleness_flag']} | "
        f"upcoming_focus={'yes' if upcoming_focus else 'no'} | "
        f"educator_note={'yes' if latest_educator_note else 'no'}"
    )

    return {
        "student_id": str(student_id),
        "class_id": str(class_id),
        "mastery": mastery,
        "weak_topics": weak_topics,
        "strong_topics": strong_topics,
        "misconceptions": misconceptions,
        "interaction_patterns": interaction_patterns,
        "engagement": engagement,
        "latest_educator_note": latest_educator_note,
        "upcoming_focus": upcoming_focus,
    }


def _compute_upcoming_focus(assessments: list[dict], weak_topics: list[str]) -> dict[str, Any] | None:
    today = date.today()
    upcoming = None
    soonest_days = None

    for assessment in assessments:
        try:
            assessment_date = date.fromisoformat(assessment["date"])
        except (KeyError, ValueError):
            continue
        if assessment_date < today:
            continue
        days_remaining = (assessment_date - today).days
        if soonest_days is None or days_remaining < soonest_days:
            soonest_days = days_remaining
            upcoming = assessment

    if upcoming is None:
        return None

    topics_in_scope = upcoming.get("covers", [])
    weak_topics_in_scope = [t for t in weak_topics if t in topics_in_scope]

    return {
        "assessment_name": upcoming.get("name", "Upcoming assessment"),
        "days_remaining": soonest_days,
        "topics_in_scope": topics_in_scope,
        "weak_topics_in_scope": weak_topics_in_scope,
    }


def check_prerequisites(student_context: dict[str, Any], query_topic: str | None, subject: str) -> list[str]:
    if not query_topic:
        return []
    required = get_prerequisites(query_topic, subject)
    return _gaps(student_context, required, query_topic)


def check_prerequisites_for_subject(
    db: Session, student_context: dict[str, Any], query_topic: str | None, subject_id: str
) -> list[str]:
    if not query_topic:
        return []
    from backend.core.prerequisites import get_prerequisites_db

    required = get_prerequisites_db(db, subject_id, query_topic)
    return _gaps(student_context, required, query_topic)


def _gaps(student_context: dict[str, Any], required: list[str], query_topic: str) -> list[str]:
    mastery = student_context["mastery"]
    gaps = [req for req in required if mastery.get(req, {}).get("score", 0.0) < 0.50]
    if gaps:
        print(f"[CONTEXT] Prerequisite gaps for topic '{query_topic}': {gaps}")
    return gaps


def detect_topic(message: str, subject: str) -> str | None:
    known_topics = list(load_prerequisite_map(subject).keys())
    lowered = message.lower()
    matches = [t for t in known_topics if t.lower() in lowered]
    detected = max(matches, key=len) if matches else None
    print(f"[CONTEXT] Topic detection (legacy): message={message[:60]!r} -> detected={detected!r}")
    return detected


TOPIC_MATCH_THRESHOLD = 0.45


def detect_topic_for_subject(
    db: Session, message: str, subject_id: str, embedding_model: Any
) -> str | None:
    from backend.pipeline.embedder import embed_single
    from backend.services import classification_service, topic_graph_service

    names, anchor_vectors = topic_graph_service.topic_anchors(db, subject_id, embedding_model)
    if not names:
        return None

    lowered = message.lower()
    substr = [n for n in names if n.lower() in lowered]
    if substr:
        detected = max(substr, key=len)
        print(f"[CONTEXT] Topic detection (substring): {detected!r}")
        return detected

    query_vec = embed_single(message, model=embedding_model)
    scored = sorted(
        ((classification_service._cosine(query_vec, av), n) for n, av in zip(names, anchor_vectors)),
        reverse=True,
    )
    best_sim, best_topic = scored[0]
    detected = best_topic if best_sim >= TOPIC_MATCH_THRESHOLD else None
    print(f"[CONTEXT] Topic detection (embedding): {detected!r} (best={best_sim:.3f} '{best_topic}')")
    return detected


def get_uploaded_topics(db: Session, class_id: str, subject: str) -> list[str]:
    from backend.models.db import Chunk, Document

    chunk_rows = (
        db.query(Chunk.text)
        .join(Document, Chunk.document_id == Document.id)
        .filter(Document.class_id == class_id, Document.deleted == False)  # noqa: E712
        .all()
    )
    combined_text = " ".join(row[0] for row in chunk_rows).lower()

    vocabulary = list(load_prerequisite_map(subject).keys())
    present = [t for t in vocabulary if t.lower() in combined_text]
    print(f"[CONTEXT] Topics actually present in class={class_id}'s uploaded content: {present}")
    return present


def check_staleness(db: Session, student_id: str) -> None:
    engagement_row = db.query(Engagement).filter(Engagement.student_id == student_id).first()
    if engagement_row is None or engagement_row.last_interaction_date is None:
        return
    if date.today() - engagement_row.last_interaction_date >= timedelta(days=5):
        engagement_row.staleness_flag = True
        db.commit()
        print(f"[CONTEXT] Staleness flag set for student {student_id} (5+ days since last interaction)")
