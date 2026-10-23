from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case, func, or_, select, true
from sqlalchemy.orm import Session

from backend.models.db import (
    ChatMessage,
    ChatSession,
    ClassEnrollment,
    EducatorNote,
    InteractionPattern,
    Misconception,
    ReflectionCluster,
    TopicMastery,
    User,
)

TRENDING_WINDOW_DAYS = 7
STRUGGLING_THRESHOLD = 0.4
AT_RISK_THRESHOLD = 0.5
FLAGGED_PAGE_SIZE = 50


def _subject_scope(column, subject_id):
    if not subject_id:
        return true()
    return or_(column == subject_id, column.is_(None))


def get_class_heatmap(db: Session, class_id: str, subject_id: str | None = None) -> list[dict[str, Any]]:
    # Only include students who are *currently* enrolled so that a student who
    # left the class no longer skews the educator's heatmap.
    enrolled_ids = select(ClassEnrollment.student_id).where(ClassEnrollment.class_id == class_id)
    rows = (
        db.query(
            TopicMastery.topic,
            func.avg(TopicMastery.mastery_score).label("average_mastery"),
            func.count(func.distinct(TopicMastery.student_id)).label("student_count"),
            func.sum(case((TopicMastery.mastery_score < STRUGGLING_THRESHOLD, 1), else_=0)).label("struggling"),
        )
        .filter(
            TopicMastery.class_id == class_id,
            TopicMastery.student_id.in_(enrolled_ids),
            _subject_scope(TopicMastery.subject_id, subject_id),
        )
        .group_by(TopicMastery.topic)
        .all()
    )
    heatmap = [
        {
            "topic": row.topic,
            "average_mastery": round(float(row.average_mastery), 3),
            "student_count": row.student_count,
            "struggling_count": int(row.struggling or 0),
        }
        for row in rows
    ]
    heatmap.sort(key=lambda h: h["average_mastery"])
    return heatmap


def get_common_misconceptions(db: Session, class_id: str, subject_id: str | None = None) -> list[dict[str, Any]]:
    # Only include students who are *currently* enrolled so that a student who
    # left the class no longer appears in the educator's misconception summary.
    enrolled_ids = select(ClassEnrollment.student_id).where(ClassEnrollment.class_id == class_id)
    rows = (
        db.query(
            Misconception.topic,
            Misconception.description,
            func.count(Misconception.id).label("count"),
        )
        .filter(
            Misconception.class_id == class_id,
            Misconception.student_id.in_(enrolled_ids),
            Misconception.resolved == False,  # noqa: E712
            _subject_scope(Misconception.subject_id, subject_id),
        )
        .group_by(Misconception.topic, Misconception.description)
        .order_by(func.count(Misconception.id).desc())
        .limit(50)
        .all()
    )
    return [{"topic": r.topic, "description": r.description, "count": r.count} for r in rows]


def _assessment_scope(class_context: dict[str, Any]) -> tuple[set[str], int | None]:
    today = datetime.utcnow().date()
    scope_topics: set[str] = set()
    days_remaining = None
    for a in class_context.get("assessments", []):
        try:
            a_date = datetime.fromisoformat(a["date"]).date()
        except (KeyError, ValueError, TypeError):
            continue
        if a_date >= today:
            scope_topics.update(a.get("covers", []))
            candidate_days = (a_date - today).days
            if days_remaining is None or candidate_days < days_remaining:
                days_remaining = candidate_days
    return scope_topics, days_remaining


def get_at_risk_students(
    db: Session, class_id: str, class_context: dict[str, Any], subject_id: str | None = None
) -> list[dict[str, Any]]:
    scope_topics, days_remaining = _assessment_scope(class_context)
    if not scope_topics:
        return []

    students = (
        db.query(User)
        .join(ClassEnrollment, ClassEnrollment.student_id == User.id)
        .filter(ClassEnrollment.class_id == class_id)
        .order_by(User.full_name)
        .all()
    )
    mastery_rows = (
        db.query(TopicMastery.student_id, TopicMastery.topic, TopicMastery.mastery_score)
        .filter(
            TopicMastery.class_id == class_id,
            TopicMastery.topic.in_(scope_topics),
            _subject_scope(TopicMastery.subject_id, subject_id),
        )
        .all()
    )
    mastery: dict[Any, dict[str, float]] = {}
    for row in mastery_rows:
        mastery.setdefault(row.student_id, {})[row.topic] = row.mastery_score

    at_risk = []
    for student in students:
        by_topic = mastery.get(student.id, {})
        weak_in_scope = sorted(t for t in scope_topics if by_topic.get(t, 0.0) < AT_RISK_THRESHOLD)
        if weak_in_scope:
            at_risk.append({
                "student_id": str(student.id),
                "full_name": student.full_name,
                "email": student.email,
                "weak_topics_in_scope": weak_in_scope,
                "days_remaining": days_remaining,
            })
    return at_risk


def get_trending_topics(db: Session, class_id: str, subject_id: str | None = None) -> list[dict[str, Any]]:
    cutoff = datetime.utcnow() - timedelta(days=TRENDING_WINDOW_DAYS)
    enrolled = db.query(ClassEnrollment.student_id).filter(ClassEnrollment.class_id == class_id)
    rows = (
        db.query(
            InteractionPattern.topic,
            func.sum(InteractionPattern.questions_asked).label("total_questions"),
        )
        .filter(
            or_(
                InteractionPattern.class_id == class_id,
                (InteractionPattern.class_id.is_(None)) & (InteractionPattern.student_id.in_(enrolled)),
            ),
            InteractionPattern.last_asked_at >= cutoff,
            _subject_scope(InteractionPattern.subject_id, subject_id),
        )
        .group_by(InteractionPattern.topic)
        .order_by(func.sum(InteractionPattern.questions_asked).desc())
        .limit(20)
        .all()
    )
    return [{"topic": r.topic, "questions_asked": int(r.total_questions)} for r in rows]


def get_class_confusion(db: Session, class_id: str, subject_id: str | None) -> list[dict[str, Any]]:
    if not subject_id:
        return []
    rows = (
        db.query(ReflectionCluster)
        .filter(ReflectionCluster.class_id == class_id, ReflectionCluster.subject_id == subject_id)
        .order_by(ReflectionCluster.cluster_size.desc())
        .all()
    )
    return [
        {
            "representative_text": r.representative_text,
            "cluster_size": r.cluster_size,
            "computed_at": r.computed_at.isoformat(),
        }
        for r in rows
    ]


def get_flagged_messages(
    db: Session, class_id: str, limit: int = FLAGGED_PAGE_SIZE, offset: int = 0
) -> list[dict[str, Any]]:
    rows = (
        db.query(ChatMessage, User.full_name)
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .join(User, ChatSession.student_id == User.id)
        .filter(ChatSession.class_id == class_id, ChatMessage.flagged_by_student == True)  # noqa: E712
        .order_by(ChatMessage.created_at.desc())
        .limit(max(1, min(limit, 200)))
        .offset(max(0, offset))
        .all()
    )
    return [
        {
            "message_id": str(msg.id),
            "student_name": student_name,
            "content": msg.content,
            "source_type": msg.source_type.value if msg.source_type else None,
            "created_at": msg.created_at.isoformat(),
        }
        for msg, student_name in rows
    ]


def get_educator_notes(db: Session, student_id: str, class_id: str) -> list[dict[str, Any]]:
    rows = (
        db.query(EducatorNote)
        .filter(EducatorNote.student_id == student_id, EducatorNote.class_id == class_id)
        .order_by(EducatorNote.created_at.desc())
        .limit(100)
        .all()
    )
    return [{"id": str(r.id), "note": r.note, "created_at": r.created_at.isoformat()} for r in rows]


def add_educator_note(db: Session, educator_id: str, student_id: str, class_id: str, note: str) -> dict[str, Any]:
    row = EducatorNote(educator_id=educator_id, student_id=student_id, class_id=class_id, note=note)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "note": row.note, "created_at": row.created_at.isoformat()}
