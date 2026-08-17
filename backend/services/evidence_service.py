from datetime import datetime

from sqlalchemy.orm import Session

from backend.models.db import Engagement, InteractionPattern


def record_interaction(db: Session, student_id: str, topic: str | None) -> None:
    if not topic:
        return
    pattern = (
        db.query(InteractionPattern)
        .filter(InteractionPattern.student_id == student_id, InteractionPattern.topic == topic)
        .first()
    )
    if pattern is None:
        pattern = InteractionPattern(student_id=student_id, topic=topic, questions_asked=0)
        db.add(pattern)
    pattern.questions_asked += 1
    pattern.last_asked_at = datetime.utcnow()
    db.commit()
    print(f"[EVIDENCE] interaction_patterns updated: student={student_id} topic={topic} questions_asked={pattern.questions_asked}")


def update_engagement(db: Session, student_id: str) -> None:
    engagement = db.query(Engagement).filter(Engagement.student_id == student_id).first()
    if engagement is None:
        print(f"[EVIDENCE WARNING] No Engagement row for student {student_id} — skipping.")
        return

    today = datetime.utcnow().date()
    if engagement.last_interaction_date == today:
        pass
    elif engagement.last_interaction_date is not None and (today - engagement.last_interaction_date).days == 1:
        engagement.current_streak += 1
    else:
        engagement.current_streak = 1

    engagement.longest_streak = max(engagement.longest_streak, engagement.current_streak)
    engagement.last_interaction_date = today
    engagement.staleness_flag = False
    engagement.total_messages += 1
    db.commit()
    print(f"[EVIDENCE] engagement updated: student={student_id} streak={engagement.current_streak} total_messages={engagement.total_messages}")
