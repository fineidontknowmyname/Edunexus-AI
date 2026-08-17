import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from backend.core.prerequisites import get_prerequisites, load_prerequisite_map
from backend.models.db import (
    Class,
    ClassContext,
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
        f"syllabus_entries={len(syllabus)} assessments={len(assessments)}"
    )

    return {
        "class_id": str(class_id),
        "subject": class_row.subject or "Operating Systems",
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

    print(
        f"[CONTEXT] Student context: {len(mastery)} topics tracked | "
        f"weak={weak_topics} strong={strong_topics} | "
        f"misconceptions={len(misconceptions)} | staleness={engagement['staleness_flag']} | "
        f"upcoming_focus={'yes' if upcoming_focus else 'no'}"
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
    print(f"[CONTEXT] Topic detection: message={message[:60]!r} -> detected={detected!r}")
    return detected


def check_staleness(db: Session, student_id: str) -> None:
    engagement_row = db.query(Engagement).filter(Engagement.student_id == student_id).first()
    if engagement_row is None or engagement_row.last_interaction_date is None:
        return
    if date.today() - engagement_row.last_interaction_date >= timedelta(days=5):
        engagement_row.staleness_flag = True
        db.commit()
        print(f"[CONTEXT] Staleness flag set for student {student_id} (5+ days since last interaction)")
