from sqlalchemy.orm import Session

from backend.models.db import Misconception, TopicMastery

ADEQUATE_MASTERY_THRESHOLD = 0.7

REINFORCE = "reinforce"
ADVANCE = "advance"
INTERVENE = "intervene"


def _has_unresolved_misconception(db: Session, student_id: str, class_id: str, topic: str) -> bool:
    return (
        db.query(Misconception.id)
        .filter(
            Misconception.student_id == student_id,
            Misconception.class_id == class_id,
            Misconception.topic == topic,
            Misconception.resolved == False,  # noqa: E712
        )
        .first()
        is not None
    )


def get_topic_routing(db: Session, student_id: str, class_id: str, topic: str) -> str:
    if _has_unresolved_misconception(db, student_id, class_id, topic):
        return INTERVENE

    row = (
        db.query(TopicMastery)
        .filter(
            TopicMastery.student_id == student_id,
            TopicMastery.class_id == class_id,
            TopicMastery.topic == topic,
        )
        .first()
    )
    if row and row.mastery_score >= ADEQUATE_MASTERY_THRESHOLD and row.last_quiz_passed:
        return ADVANCE
    return REINFORCE


def get_routing_map(db: Session, student_id: str, class_id: str) -> dict[str, str]:
    mastery_topics = {
        row.topic
        for row in db.query(TopicMastery.topic).filter(
            TopicMastery.student_id == student_id, TopicMastery.class_id == class_id
        )
    }
    misconception_topics = {
        row.topic
        for row in db.query(Misconception.topic).filter(
            Misconception.student_id == student_id,
            Misconception.class_id == class_id,
            Misconception.resolved == False,  # noqa: E712
        )
    }
    topics = mastery_topics | misconception_topics
    return {topic: get_topic_routing(db, student_id, class_id, topic) for topic in topics}
