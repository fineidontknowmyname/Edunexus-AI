from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.db import (
    ChatMessage,
    ChatSession,
    ClassEnrollment,
    EducatorNote,
    InteractionPattern,
    Misconception,
    TopicMastery,
    User,
)

TRENDING_WINDOW_DAYS = 7


def get_class_heatmap(db: Session, class_id: str) -> list[dict[str, Any]]:
    rows = (
        db.query(
            TopicMastery.topic,
            func.avg(TopicMastery.mastery_score).label("average_mastery"),
            func.count(func.distinct(TopicMastery.student_id)).label("student_count"),
        )
        .filter(TopicMastery.class_id == class_id)
        .group_by(TopicMastery.topic)
        .all()
    )

    heatmap = []
    for row in rows:
        struggling = (
            db.query(func.count(TopicMastery.id))
            .filter(
                TopicMastery.class_id == class_id,
                TopicMastery.topic == row.topic,
                TopicMastery.mastery_score < 0.4,
            )
            .scalar()
        )
        heatmap.append({
            "topic": row.topic,
            "average_mastery": round(float(row.average_mastery), 3),
            "student_count": row.student_count,
            "struggling_count": struggling,
        })

    heatmap.sort(key=lambda h: h["average_mastery"])
    print(f"[INSIGHTS] Heatmap for class={class_id}: {len(heatmap)} topics")
    return heatmap


def get_common_misconceptions(db: Session, class_id: str) -> list[dict[str, Any]]:
    rows = (
        db.query(
            Misconception.topic,
            Misconception.description,
            func.count(Misconception.id).label("count"),
        )
        .filter(Misconception.class_id == class_id, Misconception.resolved == False)  # noqa: E712
        .group_by(Misconception.topic, Misconception.description)
        .order_by(func.count(Misconception.id).desc())
        .all()
    )
    result = [{"topic": r.topic, "description": r.description, "count": r.count} for r in rows]
    print(f"[INSIGHTS] {len(result)} distinct unresolved misconception(s) for class={class_id}")
    return result


def get_at_risk_students(db: Session, class_id: str, class_context: dict[str, Any]) -> list[dict[str, Any]]:
    upcoming = class_context.get("assessments", [])
    today = datetime.utcnow().date()
    scope_topics: set[str] = set()
    days_remaining = None
    for a in upcoming:
        try:
            a_date = datetime.fromisoformat(a["date"]).date()
        except (KeyError, ValueError):
            continue
        if a_date >= today:
            scope_topics.update(a.get("covers", []))
            candidate_days = (a_date - today).days
            if days_remaining is None or candidate_days < days_remaining:
                days_remaining = candidate_days

    if not scope_topics:
        print(f"[INSIGHTS] No upcoming assessment scope for class={class_id} — no at-risk computation possible")
        return []

    enrollments = db.query(ClassEnrollment).filter(ClassEnrollment.class_id == class_id).all()
    at_risk = []
    for enrollment in enrollments:
        student = db.get(User, enrollment.student_id)
        if student is None:
            continue
        mastery_rows = (
            db.query(TopicMastery)
            .filter(TopicMastery.student_id == student.id, TopicMastery.class_id == class_id)
            .all()
        )
        mastery_by_topic = {m.topic: m.mastery_score for m in mastery_rows}

        weak_in_scope = [t for t in scope_topics if mastery_by_topic.get(t, 0.0) < 0.50]
        if weak_in_scope:
            at_risk.append({
                "student_id": str(student.id),
                "full_name": student.full_name,
                "email": student.email,
                "weak_topics_in_scope": weak_in_scope,
                "days_remaining": days_remaining,
            })

    print(f"[INSIGHTS] {len(at_risk)} at-risk student(s) for class={class_id}")
    return at_risk


def get_trending_topics(db: Session, class_id: str) -> list[dict[str, Any]]:
    cutoff = datetime.utcnow() - timedelta(days=TRENDING_WINDOW_DAYS)
    student_ids = [
        e.student_id for e in db.query(ClassEnrollment).filter(ClassEnrollment.class_id == class_id).all()
    ]
    if not student_ids:
        return []

    rows = (
        db.query(
            InteractionPattern.topic,
            func.sum(InteractionPattern.questions_asked).label("total_questions"),
        )
        .filter(
            InteractionPattern.student_id.in_(student_ids),
            InteractionPattern.last_asked_at >= cutoff,
        )
        .group_by(InteractionPattern.topic)
        .order_by(func.sum(InteractionPattern.questions_asked).desc())
        .all()
    )
    result = [{"topic": r.topic, "questions_asked": r.total_questions} for r in rows]
    print(f"[INSIGHTS] {len(result)} trending topic(s) for class={class_id} (last {TRENDING_WINDOW_DAYS} days)")
    return result


def get_flagged_messages(db: Session, class_id: str) -> list[dict[str, Any]]:
    rows = (
        db.query(ChatMessage, ChatSession, User)
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .join(User, ChatSession.student_id == User.id)
        .filter(ChatSession.class_id == class_id, ChatMessage.flagged_by_student == True)  # noqa: E712
        .order_by(ChatMessage.created_at.desc())
        .all()
    )
    result = [
        {
            "message_id": str(msg.id),
            "student_name": student.full_name,
            "content": msg.content,
            "source_type": msg.source_type.value if msg.source_type else None,
            "created_at": msg.created_at.isoformat(),
        }
        for msg, session, student in rows
    ]
    print(f"[INSIGHTS] {len(result)} flagged message(s) for class={class_id}")
    return result


def get_educator_notes(db: Session, student_id: str, class_id: str) -> list[dict[str, Any]]:
    rows = (
        db.query(EducatorNote)
        .filter(EducatorNote.student_id == student_id, EducatorNote.class_id == class_id)
        .order_by(EducatorNote.created_at.desc())
        .all()
    )
    return [{"id": str(r.id), "note": r.note, "created_at": r.created_at.isoformat()} for r in rows]


def add_educator_note(db: Session, educator_id: str, student_id: str, class_id: str, note: str) -> dict[str, Any]:
    row = EducatorNote(educator_id=educator_id, student_id=student_id, class_id=class_id, note=note)
    db.add(row)
    db.commit()
    db.refresh(row)
    print(f"[INSIGHTS] Educator note added: educator={educator_id} student={student_id} class={class_id}")
    return {"id": str(row.id), "note": row.note, "created_at": row.created_at.isoformat()}
