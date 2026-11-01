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
    assert rows[0]["class_id"] is None


def test_build_answer_rows_with_class_id():
    attempt_id = str(uuid.uuid4())
    student_id = str(uuid.uuid4())
    class_id = str(uuid.uuid4())
    q_id = str(uuid.uuid4())
    results = [
        {
            "question_id": q_id,
            "correct": True,
            "correct_answer": "A",
            "chosen": "A",
            "topic": "Deadlocks",
        }
    ]
    rows = build_answer_rows(attempt_id, student_id, results, class_id=class_id)
    assert len(rows) == 1
    assert rows[0]["class_id"] == uuid.UUID(class_id)


def test_build_answer_rows_points_and_selected_options():
    attempt_id = str(uuid.uuid4())
    student_id = str(uuid.uuid4())
    q1 = str(uuid.uuid4())
    q2 = str(uuid.uuid4())
    q3 = str(uuid.uuid4())

    results = [
        {
            "question_id": q1,
            "correct": True,
            "correct_answer": "Option A",
            "chosen": "Option A",
            "topic": "Scheduling",
            "earned_points": 1.5,
            "points_possible": 2.0,
        },
        {
            "question_id": q2,
            "correct": True,
            "correct_answer": ["Opt 1", "Opt 2"],
            "chosen": ["Opt 1", "Opt 2"],
            "topic": "Concurrency",
            "earned_points": 2.0,
            "points_possible": 2.0,
        },
        {
            "question_id": q3,
            "correct": False,
            "correct_answer": "True",
            "chosen": None,
            "topic": "Deadlocks",
            "earned_points": 0.0,
            "points_possible": 1.0,
        },
    ]

    rows = build_answer_rows(attempt_id, student_id, results)
    assert len(rows) == 3

    # Q1: single choice string
    assert rows[0]["points_awarded"] == 1.5
    assert rows[0]["max_points"] == 2.0
    assert rows[0]["selected_options"] == "Option A"

    # Q2: multiple choice list
    assert rows[1]["points_awarded"] == 2.0
    assert rows[1]["max_points"] == 2.0
    assert rows[1]["selected_options"] == '["Opt 1", "Opt 2"]'

    # Q3: unanswered / None
    assert rows[2]["points_awarded"] == 0.0
    assert rows[2]["max_points"] == 1.0
    assert rows[2]["selected_options"] is None
