from datetime import date, datetime, timezone
from typing import Any
import uuid

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.time_utils import effective_streak, local_today
from backend.core.tracking_constants import ENGAGEMENT_INACTIVE_DAYS
from backend.models.db import Engagement, InteractionPattern


def interaction_scope(class_id):
    return or_(InteractionPattern.class_id == class_id, InteractionPattern.class_id.is_(None))


def record_interaction(
    db: Session, student_id: str, topic: str | None, class_id=None, subject_id=None
) -> None:
    if not topic:
        return
    query = db.query(InteractionPattern).filter(
        InteractionPattern.student_id == student_id, InteractionPattern.topic == topic
    )
    query = query.filter(InteractionPattern.class_id == class_id) if class_id else query.filter(InteractionPattern.class_id.is_(None))
    pattern = query.first()
    if pattern is None:
        try:
            with db.begin_nested():
                pattern = InteractionPattern(
                    student_id=student_id,
                    topic=topic,
                    questions_asked=1,
                    class_id=class_id,
                    subject_id=subject_id,
                    last_asked_at=datetime.now(timezone.utc),
                )
                db.add(pattern)
                db.flush()
        except IntegrityError:
            query = db.query(InteractionPattern).filter(
                InteractionPattern.student_id == student_id, InteractionPattern.topic == topic
            )
            query = query.filter(InteractionPattern.class_id == class_id) if class_id else query.filter(InteractionPattern.class_id.is_(None))
            pattern = query.first()
            if pattern:
                pattern.questions_asked += 1
                pattern.last_asked_at = datetime.now(timezone.utc)
    else:
        pattern.questions_asked += 1
        pattern.last_asked_at = datetime.now(timezone.utc)
    db.commit()


def apply_activity(engagement: Any, today: date, count_as_message: bool = True) -> None:
    """
    Mutates the engagement object based on activity recorded today.
    - If last_interaction_date == today: do nothing to the streak.
    - Elif last_interaction_date is yesterday: increment current_streak.
    - Elif last_interaction_date > today (clock backwards): preserve streak and last_interaction_date.
    - Else (missed days): reset current_streak to 1.
    - Update longest_streak, last_interaction_date (unless backwards), total_messages, staleness_flag.
    """
    last = engagement.last_interaction_date
    is_backwards = False

    if last == today:
        pass
    elif last is not None and (today - last).days == 1:
        engagement.current_streak += 1
    elif last is not None and last > today:
        is_backwards = True
    else:
        engagement.current_streak = 1

    engagement.longest_streak = max(engagement.longest_streak, engagement.current_streak)
    if not is_backwards:
        engagement.last_interaction_date = today
    if count_as_message:
        engagement.total_messages += 1
    engagement.staleness_flag = False


def get_or_create_engagement(db: Session, student_id: Any, class_id: Any) -> Engagement:
    """
    Fetches or creates the class-scoped Engagement row for (student_id, class_id).
    Uses nested transaction (SAVEPOINT) to handle race conditions safely.
    Flushes only; never commits.
    """
    s_id = uuid.UUID(str(student_id)) if not isinstance(student_id, uuid.UUID) else student_id
    c_id = uuid.UUID(str(class_id)) if not isinstance(class_id, uuid.UUID) else class_id

    row = (
        db.query(Engagement)
        .filter(Engagement.student_id == s_id, Engagement.class_id == c_id)
        .first()
    )
    if row is not None:
        return row

    try:
        with db.begin_nested():
            new_row = Engagement(
                student_id=s_id,
                class_id=c_id,
                current_streak=0,
                longest_streak=0,
                last_interaction_date=None,
                staleness_flag=False,
                total_sessions=0,
                total_messages=0,
            )
            db.add(new_row)
            db.flush()
            return new_row
    except IntegrityError:
        return (
            db.query(Engagement)
            .filter(Engagement.student_id == s_id, Engagement.class_id == c_id)
            .one()
        )


def update_engagement(
    db: Session,
    student_id: Any,
    class_id: Any,
    count_as_message: bool = True,
    tz_name: str = "UTC",
) -> None:
    """
    Updates class-scoped engagement for student.
    Does NOT commit; only flushes.
    """
    if not class_id:
        print(f"[EVIDENCE WARNING] update_engagement called without class_id for student {student_id} — skipping.")
        return

    engagement = get_or_create_engagement(db, student_id, class_id)
    today = local_today(tz_name)
    apply_activity(engagement, today, count_as_message=count_as_message)
    db.flush()
    print(
        f"[EVIDENCE] engagement updated: student={student_id} class={class_id} "
        f"streak={engagement.current_streak} total_messages={engagement.total_messages}"
    )


def build_engagement_payload(row: Engagement | None, today: date) -> dict[str, Any]:
    """
    Builds the engagement dictionary for API responses.
    Calculates streak expiry and inactivity dynamically on read.
    Does NOT write to the database.
    """
    if row is None:
        return {
            "current_streak": 0,
            "longest_streak": 0,
            "total_messages": 0,
            "total_sessions": 0,
            "last_interaction_date": None,
            "has_activity": False,
            "is_inactive": False,
            "staleness_flag": False,
        }

    has_activity = row.last_interaction_date is not None
    cur_streak = effective_streak(row.current_streak, row.last_interaction_date, today)
    is_inactive = (
        has_activity and (today - row.last_interaction_date).days >= ENGAGEMENT_INACTIVE_DAYS
    )

    return {
        "current_streak": cur_streak,
        "longest_streak": row.longest_streak,
        "total_messages": row.total_messages,
        "total_sessions": row.total_sessions,
        "last_interaction_date": row.last_interaction_date.isoformat() if row.last_interaction_date else None,
        "has_activity": has_activity,
        "is_inactive": is_inactive,
        "staleness_flag": is_inactive,
    }
