import sys
from datetime import datetime, timedelta

sys.path.insert(0, ".")

from backend.core.database import SessionLocal
from backend.core.security import hash_password
from backend.models.db import (
    Class,
    ClassEnrollment,
    Engagement,
    InteractionPattern,
    Misconception,
    MasteryTrend,
    TopicMastery,
    User,
    UserRole,
)

CLASS_ID = "d6ce41d2-bc69-4cfc-b72a-0727b0d1b600"

DEMO_STUDENTS = [
    {
        "email": "priya.sharma@demo.edunexus.ai",
        "full_name": "Priya Sharma",
        "password": "demo1234",
        "mastery": {
            "FCFS": (0.92, MasteryTrend.stable, 6),
            "SJF": (0.87, MasteryTrend.stable, 5),
            "Round Robin": (0.85, MasteryTrend.improving, 4),
            "Process Synchronization": (0.78, MasteryTrend.improving, 3),
            "Deadlock Detection": (0.70, MasteryTrend.improving, 2),
        },
        "interactions": {
            "FCFS": 2, "SJF": 3, "Round Robin": 1, "Process Synchronization": 2, "Deadlock Detection": 1,
        },
        "misconceptions": [],
        "streak": 12,
        "longest_streak": 14,
        "staleness_flag": False,
    },
    {
        "email": "rahul.verma@demo.edunexus.ai",
        "full_name": "Rahul Verma",
        "password": "demo1234",
        "mastery": {
            "FCFS": (0.62, MasteryTrend.stable, 3),
            "SJF": (0.38, MasteryTrend.declining, 4),
            "Round Robin": (0.45, MasteryTrend.stable, 2),
            "Process Synchronization": (0.0, MasteryTrend.not_started, 0),
            "Deadlock Detection": (0.0, MasteryTrend.not_started, 0),
        },
        "interactions": {
            "FCFS": 2, "SJF": 4, "Round Robin": 1,
        },
        "misconceptions": [
            {"topic": "SJF", "description": "Conflates burst time with arrival time when ranking jobs."},
        ],
        "streak": 3,
        "longest_streak": 5,
        "staleness_flag": False,
    },
]


def seed():
    db = SessionLocal()
    try:
        class_row = db.query(Class).filter(Class.id == CLASS_ID).first()
        if class_row is None:
            print(f"[SEED] Class {CLASS_ID} not found. Aborting.")
            return

        for spec in DEMO_STUDENTS:
            existing = db.query(User).filter(User.email == spec["email"]).first()
            if existing:
                print(f"[SEED] Removing existing demo user {spec['email']} to reseed clean.")
                db.delete(existing)
                db.commit()

            user = User(
                email=spec["email"],
                hashed_password=hash_password(spec["password"]),
                full_name=spec["full_name"],
                role=UserRole.student,
                created_at=datetime.utcnow() - timedelta(days=28),
            )
            db.add(user)
            db.flush()

            db.add(ClassEnrollment(class_id=CLASS_ID, student_id=user.id, enrolled_at=user.created_at))

            for topic, (score, trend, attempts) in spec["mastery"].items():
                db.add(TopicMastery(
                    student_id=user.id,
                    class_id=CLASS_ID,
                    topic=topic,
                    mastery_score=score,
                    attempt_count=attempts,
                    trend=trend,
                    last_attempt_at=datetime.utcnow() - timedelta(days=1) if attempts else None,
                ))

            for topic, count in spec["interactions"].items():
                db.add(InteractionPattern(
                    student_id=user.id,
                    topic=topic,
                    questions_asked=count,
                    last_asked_at=datetime.utcnow() - timedelta(days=1),
                ))

            for m in spec["misconceptions"]:
                db.add(Misconception(
                    student_id=user.id,
                    class_id=CLASS_ID,
                    topic=m["topic"],
                    description=m["description"],
                    detected_at=datetime.utcnow() - timedelta(days=2),
                ))

            db.add(Engagement(
                student_id=user.id,
                current_streak=spec["streak"],
                longest_streak=spec["longest_streak"],
                last_interaction_date=(datetime.utcnow() - timedelta(days=1)).date(),
                staleness_flag=spec["staleness_flag"],
                total_sessions=spec["streak"],
                total_messages=spec["streak"] * 4,
            ))

            db.commit()
            print(f"[SEED] Seeded {spec['full_name']} ({spec['email']}) into class {CLASS_ID}.")

        print("[SEED] Done. Login with either demo account using password 'demo1234'.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
