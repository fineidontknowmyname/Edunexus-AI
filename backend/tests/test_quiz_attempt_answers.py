from datetime import datetime, timezone
import uuid
import pytest

from backend.services.quiz_service import build_answer_rows


def test_build_answer_rows_basic():
    attempt_id = str(uuid.uuid4())
    student_id = str(uuid.uuid4())
    q1_id = str(uuid.uuid4())
    q2_id = str(uuid.uuid4())
    fixed_time = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)

    results = [
        {
            "question_id": q1_id,
            "correct": True,
            "correct_answer": "Option A",
            "chosen": "Option A",
            "topic": "Process Scheduling",
            "difficulty": "medium",
            "option_count": 4,
        },
        {
            "question_id": q2_id,
            "correct": False,
            "correct_answer": "Option C",
            "chosen": "Option B",
            "topic": "Virtual Memory",
            "difficulty": "hard",
            "option_count": 4,
        },
    ]

    rows = build_answer_rows(attempt_id, student_id, results, answered_at=fixed_time)
    assert len(rows) == 2

    r1, r2 = rows[0], rows[1]
    assert r1["attempt_id"] == uuid.UUID(attempt_id)
    assert r1["student_id"] == uuid.UUID(student_id)
    assert r1["question_id"] == uuid.UUID(q1_id)
    assert r1["topic"] == "Process Scheduling"
    assert r1["topic_key"] == "process scheduling"
    assert r1["is_correct"] is True
    assert r1["difficulty"] == "medium"
    assert r1["option_count"] == 4
    assert r1["answered_at"] == fixed_time

    assert r2["question_id"] == uuid.UUID(q2_id)
    assert r2["topic_key"] == "virtual memory"
    assert r2["is_correct"] is False
    assert r2["difficulty"] == "hard"


def test_build_answer_rows_missing_topic_and_empty():
    attempt_id = str(uuid.uuid4())
    student_id = str(uuid.uuid4())

    # Empty results
    assert build_answer_rows(attempt_id, student_id, []) == []

    # Missing topic / None topic
    q_id = str(uuid.uuid4())
    results = [
        {
            "question_id": q_id,
            "correct": True,
            "correct_answer": "Ans",
            "chosen": "Ans",
            "topic": None,
        }
    ]
    rows = build_answer_rows(attempt_id, student_id, results)
    assert len(rows) == 1
    assert rows[0]["topic"] is None
    assert rows[0]["topic_key"] is None
    assert rows[0]["difficulty"] is None
    assert rows[0]["option_count"] is None
