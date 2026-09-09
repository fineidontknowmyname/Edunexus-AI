"""Behavioural learning-tag tracking (Chunk 2.3).

Per student, per topic, per subject: message count, follow-up rate, and a
deterministic question-type split (conceptual / example-seeking /
direct-answer-seeking). A small set of interpretable tags is derived from
threshold rules over those counters. This is a routing proxy, NOT a validated
learning-styles classifier.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from backend.models.db import TopicBehavior

_EXAMPLE_PATTERNS = re.compile(
    r"\b(example|for instance|show me|walk me through|worked|demonstrat|illustrat|sample|e\.g\.)\b",
    re.IGNORECASE,
)
_CONCEPTUAL_PATTERNS = re.compile(
    r"\b(why|how does|what is|explain|meaning|concept|intuition|difference between|reason)\b",
    re.IGNORECASE,
)
_DIRECT_PATTERNS = re.compile(
    r"\b(answer|just tell me|what's the|whats the|give me the|solution|correct option|which one)\b",
    re.IGNORECASE,
)
_FOLLOW_UP_PATTERNS = re.compile(
    r"^\s*(why|how|and\b|but\b|so\b|explain more|elaborate|go on|continue|more detail|still (don'?t|not) (get|understand))",
    re.IGNORECASE,
)

FOLLOW_UP_MAX_WORDS = 8


def classify_question_type(message: str) -> str:
    if _EXAMPLE_PATTERNS.search(message):
        return "example"
    if _DIRECT_PATTERNS.search(message):
        return "direct"
    if _CONCEPTUAL_PATTERNS.search(message):
        return "conceptual"
    return "conceptual"


def is_follow_up(message: str, last_role: str | None) -> bool:
    if last_role != "assistant":
        return False
    if _FOLLOW_UP_PATTERNS.search(message):
        return True
    return len(message.split()) <= FOLLOW_UP_MAX_WORDS and message.rstrip().endswith("?")


def _derive_tag(row: TopicBehavior) -> str | None:
    total_qt = row.qt_conceptual + row.qt_example + row.qt_direct
    if total_qt < 3:
        return None
    if row.message_count >= 4 and row.follow_up_count / max(row.message_count, 1) >= 0.5:
        return "needs-repetition"
    if row.qt_example / total_qt >= 0.5:
        return "example-driven"
    if row.qt_conceptual / total_qt >= 0.6:
        return "concept-first"
    return None


def record_turn(
    db: Session,
    student_id: str,
    subject_id: str | None,
    topic: str | None,
    message: str,
    last_role: str | None,
) -> str | None:
    """Update counters for (student, subject, topic) and return the derived tag."""
    if not topic or not subject_id:
        return None

    row = (
        db.query(TopicBehavior)
        .filter(
            TopicBehavior.student_id == student_id,
            TopicBehavior.subject_id == subject_id,
            TopicBehavior.topic == topic,
        )
        .first()
    )
    if row is None:
        row = TopicBehavior(
            student_id=student_id,
            subject_id=subject_id,
            topic=topic,
            message_count=0,
            follow_up_count=0,
            qt_conceptual=0,
            qt_example=0,
            qt_direct=0,
        )
        db.add(row)

    row.message_count += 1
    if is_follow_up(message, last_role):
        row.follow_up_count += 1

    qt = classify_question_type(message)
    if qt == "example":
        row.qt_example += 1
    elif qt == "direct":
        row.qt_direct += 1
    else:
        row.qt_conceptual += 1

    row.learning_tag = _derive_tag(row)
    db.commit()
    print(
        f"[BEHAVIOR] student={student_id} topic={topic!r} qt={qt} "
        f"follow_up={row.follow_up_count}/{row.message_count} -> tag={row.learning_tag!r}"
    )
    return row.learning_tag


def get_learning_tag(db: Session, student_id: str, subject_id: str | None, topic: str | None) -> str | None:
    if not topic or not subject_id:
        return None
    row = (
        db.query(TopicBehavior)
        .filter(
            TopicBehavior.student_id == student_id,
            TopicBehavior.subject_id == subject_id,
            TopicBehavior.topic == topic,
        )
        .first()
    )
    return row.learning_tag if row else None
