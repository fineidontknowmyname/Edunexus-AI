from datetime import datetime, timezone
from unittest.mock import MagicMock
import uuid
import pytest
from fastapi import HTTPException

from backend.models.db import Quiz, QuizAttempt, QuizAttemptAnswer, QuizQuestion, User
from backend.api.quizzes import get_attempt_detail, _claim_submission
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


def test_get_attempt_detail_returns_200_with_real_answer_rows():
    student_id = uuid.uuid4()
    attempt_id = uuid.uuid4()
    q_id = uuid.uuid4()

    quiz = Quiz(id=uuid.uuid4(), title="Test Quiz", class_id=uuid.uuid4(), version=1, passing_percentage=60.0)
    question = QuizQuestion(
        id=q_id,
        quiz_id=quiz.id,
        question_text="What is an OS?",
        options='["A", "B"]',
        correct_answer="A",
        points=2.0,
        question_type="multiple_choice",
    )
    quiz.questions = [question]
    attempt = QuizAttempt(
        id=attempt_id,
        student_id=student_id,
        quiz_id=quiz.id,
        quiz=quiz,
        quiz_version=1,
        score=75.0,
        answers="{}",
        topic_scores='{"OS": 0.75}',
        completed=True,
        completed_at=datetime.now(timezone.utc),
    )
    ans = QuizAttemptAnswer(
        id=uuid.uuid4(),
        attempt_id=attempt_id,
        student_id=student_id,
        question_id=q_id,
        topic="OS",
        topic_key="os",
        is_correct=True,
        points_awarded=1.5,
        max_points=2.0,
        answered_at=datetime.now(timezone.utc),
    )

    mock_db = MagicMock()

    def query_side_effect(model):
        mock_query = MagicMock()
        if model == QuizAttempt:
            mock_query.filter.return_value.first.return_value = attempt
        elif model == QuizAttemptAnswer:
            mock_query.filter.return_value.all.return_value = [ans]
        else:
            mock_query.filter.return_value.all.return_value = []
        return mock_query

    mock_db.query.side_effect = query_side_effect

    user = User(id=student_id)
    res = get_attempt_detail(str(attempt_id), db=mock_db, current_user=user, _student=None)

    assert res["score"] == 75.0
    assert res["score_ratio"] == 0.75
    assert res["passing_ratio"] == 0.60
    assert len(res["results"]) == 1
    assert res["results"][0]["points_possible"] == 2.0
    assert res["results"][0]["earned_points"] == 1.5


def test_claim_submission_retake_window_and_duplicate_conflict():
    student_id = uuid.uuid4()
    quiz = Quiz(id=uuid.uuid4(), title="Test Quiz", version=1)
    user = User(id=student_id)
    answers_json = '{"q1": "A"}'

    # Case A: duplicate submission within 30-second window raises HTTP 409
    mock_db_recent = MagicMock()
    recent_attempt = QuizAttempt(id=uuid.uuid4(), student_id=student_id, quiz_id=quiz.id)
    mock_db_recent.query.return_value.filter.return_value.one.return_value = user
    mock_db_recent.query.return_value.filter.return_value.first.return_value = recent_attempt

    with pytest.raises(HTTPException) as exc_info:
        _claim_submission(mock_db_recent, quiz, user, answers_json)
    assert exc_info.value.status_code == 409
    assert "already received" in exc_info.value.detail

    # Verify filter args: started_at >= 30s window must be present, completed must NOT be present
    filter_args = [str(arg) for arg in mock_db_recent.query.return_value.filter.call_args[0]]
    assert any("started_at >=" in a for a in filter_args), "Missing started_at >= condition"
    assert not any("completed" in a.lower() for a in filter_args), "Unexpected completed condition in duplicate check"

    # Case B: resubmission with same answers after window (query returns None) is accepted
    mock_db_allowed = MagicMock()
    mock_db_allowed.query.return_value.filter.return_value.one.return_value = user
    mock_db_allowed.query.return_value.filter.return_value.first.return_value = None

    claimed = _claim_submission(mock_db_allowed, quiz, user, answers_json)
    assert claimed is not None
    assert claimed.student_id == student_id
    assert claimed.quiz_id == quiz.id
    assert claimed.answers == answers_json
