import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from backend.core.prerequisites import load_prerequisite_map
from backend.models.db import Engagement, InteractionPattern, MasteryTrend, Quiz, QuizAttempt, TopicMastery
from backend.services import context_service

STALE_AFTER_DAYS = 7


def calculate_mastery(scores_most_recent_first: list[float]) -> float:
    n = len(scores_most_recent_first)
    if n == 0:
        return 0.0
    if n == 1:
        return scores_most_recent_first[0]
    if n == 2:
        return scores_most_recent_first[0] * 0.6 + scores_most_recent_first[1] * 0.4

    recent = scores_most_recent_first[0] * 0.5 + scores_most_recent_first[1] * 0.3
    older = scores_most_recent_first[2:]
    return recent + (sum(older) / len(older)) * 0.2


def calculate_trend(scores_most_recent_first: list[float]) -> MasteryTrend:
    if len(scores_most_recent_first) < 3:
        return MasteryTrend.not_started if not scores_most_recent_first else MasteryTrend.stable
    last_3 = scores_most_recent_first[:3]
    if last_3[0] > last_3[1] > last_3[2]:
        return MasteryTrend.improving
    if last_3[0] < last_3[1] < last_3[2]:
        return MasteryTrend.declining
    return MasteryTrend.stable


def _topic_score_history(db: Session, student_id: str, class_id: str, topic: str) -> list[float]:
    attempts = (
        db.query(QuizAttempt)
        .join(Quiz, QuizAttempt.quiz_id == Quiz.id)
        .filter(
            QuizAttempt.student_id == student_id,
            Quiz.class_id == class_id,
            QuizAttempt.completed == True,  # noqa: E712
        )
        .order_by(QuizAttempt.completed_at.desc())
        .all()
    )
    scores: list[float] = []
    for attempt in attempts:
        if not attempt.topic_scores:
            continue
        try:
            topic_scores: dict[str, float] = json.loads(attempt.topic_scores)
        except json.JSONDecodeError:
            continue
        if topic in topic_scores:
            scores.append(topic_scores[topic])
    return scores


def update_mastery_after_attempt(
    db: Session,
    student_id: str,
    class_id: str,
    topic_scores: dict[str, float],
    topic_passed: dict[str, bool] | None = None,
) -> dict[str, Any]:
    topic_passed = topic_passed or {}
    updated_topics = {}
    for topic in topic_scores:
        history = _topic_score_history(db, student_id, class_id, topic)
        mastery_score = calculate_mastery(history)
        trend = calculate_trend(history)
        attempt_count = len(history)

        row = (
            db.query(TopicMastery)
            .filter(TopicMastery.student_id == student_id, TopicMastery.class_id == class_id, TopicMastery.topic == topic)
            .first()
        )
        if row is None:
            row = TopicMastery(student_id=student_id, class_id=class_id, topic=topic)
            db.add(row)

        row.mastery_score = mastery_score
        row.attempt_count = attempt_count
        row.trend = trend
        row.last_attempt_at = datetime.utcnow()
        if topic in topic_passed:
            row.last_quiz_passed = topic_passed[topic]

        updated_topics[topic] = {
            "mastery_score": mastery_score,
            "trend": trend.value,
            "attempt_count": attempt_count,
            "last_quiz_passed": row.last_quiz_passed,
        }
        print(f"[PROGRESS] Mastery updated: student={student_id} topic={topic} score={mastery_score:.3f} trend={trend.value} attempts={attempt_count}")

    db.commit()
    return updated_topics


def _assign_priority(attempted: bool, score: float, in_scope: bool, days_remaining: int | None) -> int:
    if attempted and score < 0.40:
        return 0
    if not attempted and in_scope and days_remaining is not None and days_remaining <= 7:
        return 1
    if attempted and 0.40 <= score < 0.60:
        return 2
    if not attempted:
        return 3
    if 0.60 <= score < 0.80:
        return 4
    return 5


def get_learning_path(db: Session, student_id: str, class_id: str) -> dict[str, Any]:
    student_context = context_service.assemble_student_context(db, student_id, class_id)
    class_context = context_service.assemble_class_context(db, class_id)

    vocabulary = list(load_prerequisite_map(class_context["subject"]).keys())
    uploaded_topics = set(context_service.get_uploaded_topics(db, class_id, class_context["subject"]))
    mastery = student_context["mastery"]
    already_tracked = set(mastery.keys())
    syllabus_topics = [t for t in vocabulary if t in uploaded_topics or t in already_tracked]
    upcoming = student_context.get("upcoming_focus")
    topics_in_scope = set(upcoming["topics_in_scope"]) if upcoming else set()
    days_remaining = upcoming["days_remaining"] if upcoming else None

    entries = []
    for index, topic in enumerate(syllabus_topics):
        entry = mastery.get(topic)
        attempted = bool(entry and entry["attempts"] > 0)
        score = entry["score"] if entry else 0.0
        in_scope = topic in topics_in_scope
        priority = _assign_priority(attempted, score, in_scope, days_remaining)

        entries.append({
            "topic": topic,
            "priority": priority,
            "mastery_score": score,
            "attempts": entry["attempts"] if entry else 0,
            "trend": entry["trend"] if entry else "not_started",
            "in_assessment_scope": in_scope,
            "syllabus_index": index,
        })

    entries.sort(key=lambda e: (e["priority"], 0 if e["in_assessment_scope"] else 1, e["syllabus_index"]))

    cold_start = len(mastery) == 0
    print(f"[PROGRESS] Learning path built: {len(entries)} topics, cold_start={cold_start}")

    return {"cold_start": cold_start, "path": entries}


def get_dashboard(db: Session, student_id: str, class_id: str) -> dict[str, Any]:
    student_context = context_service.assemble_student_context(db, student_id, class_id)
    mastery = student_context["mastery"]

    engagement_row = db.query(Engagement).filter(Engagement.student_id == student_id).first()
    engagement = {
        "current_streak": engagement_row.current_streak if engagement_row else 0,
        "longest_streak": engagement_row.longest_streak if engagement_row else 0,
        "staleness_flag": engagement_row.staleness_flag if engagement_row else False,
    }

    now = datetime.utcnow()
    stale_cutoff = now - timedelta(days=STALE_AFTER_DAYS)
    interaction_rows = db.query(InteractionPattern).filter(InteractionPattern.student_id == student_id).all()
    last_touched: dict[str, datetime] = {}
    for row in interaction_rows:
        if row.last_asked_at:
            last_touched[row.topic] = row.last_asked_at

    mastery_rows = db.query(TopicMastery).filter(
        TopicMastery.student_id == student_id, TopicMastery.class_id == class_id
    ).all()
    for row in mastery_rows:
        if row.last_attempt_at and (row.topic not in last_touched or row.last_attempt_at > last_touched[row.topic]):
            last_touched[row.topic] = row.last_attempt_at

    stale_topics = [topic for topic, last in last_touched.items() if last < stale_cutoff]

    print(f"[PROGRESS] Dashboard built for student={student_id}: {len(mastery)} topics tracked, {len(stale_topics)} stale")

    return {
        "mastery": [
            {"topic": topic, "score": v["score"], "trend": v["trend"], "attempts": v["attempts"]}
            for topic, v in mastery.items()
        ],
        "engagement": engagement,
        "upcoming_focus": student_context.get("upcoming_focus"),
        "stale_topics": stale_topics,
    }
