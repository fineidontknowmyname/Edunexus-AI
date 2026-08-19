import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.models.db import MasteryTrend, Quiz, QuizAttempt, TopicMastery


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
    db: Session, student_id: str, class_id: str, topic_scores: dict[str, float]
) -> dict[str, Any]:
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

        updated_topics[topic] = {"mastery_score": mastery_score, "trend": trend.value, "attempt_count": attempt_count}
        print(f"[PROGRESS] Mastery updated: student={student_id} topic={topic} score={mastery_score:.3f} trend={trend.value} attempts={attempt_count}")

    db.commit()
    return updated_topics
