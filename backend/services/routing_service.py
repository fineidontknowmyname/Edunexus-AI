from sqlalchemy.orm import Session

from backend.core.tracking_constants import MASTERED_THRESHOLD
from backend.models.db import Misconception, TopicMastery

ADEQUATE_MASTERY_THRESHOLD = MASTERED_THRESHOLD

REINFORCE = "reinforce"
ADVANCE = "advance"
INTERVENE = "intervene"


def intervene_topics(db: Session, student_id: str, class_id: str) -> set[str]:
    rows = db.query(Misconception.topic).filter(
        Misconception.student_id == student_id,
        Misconception.class_id == class_id,
        Misconception.resolved == False,  # noqa: E712
    )
    return {row.topic for row in rows if row.topic and row.topic.strip() and row.topic.strip().lower() != "general"}


def _label(row: TopicMastery | None) -> str:
    if row is not None and row.mastery_score >= ADEQUATE_MASTERY_THRESHOLD and row.last_quiz_passed:
        return ADVANCE
    return REINFORCE


def get_topic_routing(db: Session, student_id: str, class_id: str, topic: str) -> str:
    if topic in intervene_topics(db, student_id, class_id):
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
    return _label(row)


def get_routing_map(db: Session, student_id: str, class_id: str) -> dict[str, str]:
    locked = intervene_topics(db, student_id, class_id)
    mastery_rows = {
        row.topic: row
        for row in db.query(TopicMastery).filter(
            TopicMastery.student_id == student_id, TopicMastery.class_id == class_id
        )
    }
    topics = set(mastery_rows) | locked
    return {topic: INTERVENE if topic in locked else _label(mastery_rows.get(topic)) for topic in topics}
