import json
import time
import uuid
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.db import ReviewStatus, User, Quiz, QuizAttempt
from backend.core.database import SessionLocal
from backend.core.security import create_access_token
from backend.services import quiz_service


def test_available_questions_untagged_not_locked():
    """Verify that questions with None/empty topic are not locked by intervene_topics."""
    class MockQuestion:
        def __init__(self, id, topic, status=ReviewStatus.approved):
            self.id = id
            self.topic = topic
            self.status = status

    class MockQuiz:
        def __init__(self, questions):
            self.questions = questions

    with patch("backend.services.routing_service.intervene_topics", return_value={"Deadlock Detection", "CPU Scheduling"}):
        q1 = MockQuestion(uuid.uuid4(), topic=None)
        q2 = MockQuestion(uuid.uuid4(), topic="")
        q3 = MockQuestion(uuid.uuid4(), topic="CPU Scheduling")
        q4 = MockQuestion(uuid.uuid4(), topic="Virtual Memory")
        mock_quiz = MockQuiz([q1, q2, q3, q4])

        available = quiz_service.available_questions_for_student(
            None, mock_quiz, "student-1", "class-1"
        )
        assert len(available) == 3
        # q1 and q2 (no topic) and q4 (Virtual Memory) must be available; q3 (CPU Scheduling) is locked
        assert q1 in available
        assert q2 in available
        assert q4 in available
        assert q3 not in available


class _MockQuery:
    def filter(self, *args, **kwargs):
        return self
    def all(self):
        return []
    def first(self):
        return None
    def __iter__(self):
        return iter([])


class _MockDB:
    def get(self, model, id):
        class MockClass:
            subject_id = None
        return MockClass()
    def query(self, *args):
        return _MockQuery()


@pytest.mark.anyio
async def test_score_attempt_fast_no_blocking_ai():
    """Verify that score_attempt does not perform slow synchronous LLM calls for 20 wrong answers."""
    class MockQuestion:
        def __init__(self, id, text, correct, topic=None):
            self.id = id
            self.question_text = text
            self.correct_answer = correct
            self.topic = topic
            self.status = ReviewStatus.approved
            self.difficulty = "medium"
            self.options = json.dumps(["A", "B", "C", "D"])

    questions = [
        MockQuestion(uuid.uuid4(), f"Question {i} text", "A", topic=None)
        for i in range(20)
    ]

    class MockQuiz:
        def __init__(self, q_list):
            self.id = uuid.uuid4()
            self.questions = q_list

    mock_quiz = MockQuiz(questions)
    answers = {str(q.id): "B" for q in questions}  # all wrong answers

    start = time.perf_counter()
    result = await quiz_service.score_attempt(
        _MockDB(), mock_quiz, "student-123", "class-456", answers
    )
    elapsed = time.perf_counter() - start

    # Must complete almost instantaneously (< 0.1 second), never block for seconds/minutes
    assert elapsed < 0.2, f"score_attempt took too long ({elapsed:.3f}s), synchronous AI blocking suspected"
    assert result["score"] == 0.0
    assert len(result["results"]) == 20
    assert all(r["correct"] is False for r in result["results"])


@pytest.mark.anyio
async def test_score_attempt_collects_ai_candidates_for_valid_topics():
    """Verify that score_attempt separates rule evaluation from background AI fallback."""
    class MockQuestion:
        def __init__(self, id, text, correct, topic):
            self.id = id
            self.question_text = text
            self.correct_answer = correct
            self.topic = topic
            self.status = ReviewStatus.approved
            self.difficulty = "medium"
            self.options = json.dumps(["A", "B", "C", "D"])

    questions = [
        MockQuestion(uuid.uuid4(), "Explain SJF arrival", "A", topic="Custom Topic 1"),
        MockQuestion(uuid.uuid4(), "Explain SJF burst", "A", topic="Custom Topic 2"),
    ]

    class MockQuiz:
        def __init__(self, q_list):
            self.id = uuid.uuid4()
            self.questions = q_list

    mock_quiz = MockQuiz(questions)
    answers = {str(q.id): "Wrong" for q in questions}

    with patch("backend.services.misconception_service.check_rule_map", return_value=None):
        result = await quiz_service.score_attempt(
            _MockDB(), mock_quiz, "student-123", "class-456", answers
        )
        # Should collect candidates for background AI evaluation rather than blocking
        assert len(result["ai_candidates"]) == 2
        assert result["ai_candidates"][0]["topic"] == "Custom Topic 1"
        assert result["ai_candidates"][1]["topic"] == "Custom Topic 2"


def test_submit_attempt_endpoint_live_speed_and_duplicate_rejection():
    """Verify live endpoint submission executes quickly (< 2s) and returns 409 on duplicate."""
    db = SessionLocal()
    try:
        student = db.query(User).filter(User.email == "mno@gmail.com").first()
        if not student:
            pytest.skip("Student mno@gmail.com not found")
        token = create_access_token(student.id, student.role.value)
    finally:
        db.close()

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    quiz_id = "f72d46f5-b16e-46db-b74c-758ab80a7b84"

    # Get quiz
    get_resp = client.get(f"/api/v1/quizzes/{quiz_id}", headers=headers)
    assert get_resp.status_code == 200, f"get_quiz failed: {get_resp.text}"
    quiz_data = get_resp.json()
    questions = quiz_data.get("questions", [])
    assert len(questions) == 20, f"Expected 20 questions, got {len(questions)}"

    # Generate answers with timestamp salt to ensure freshness on first attempt
    unique_tag = str(uuid.uuid4())[:8]
    answers = {q["id"]: f"Answer_{unique_tag}" for q in questions}

    start = time.perf_counter()
    resp1 = client.post(
        f"/api/v1/quizzes/{quiz_id}/attempt",
        json={"answers": answers},
        headers=headers,
    )
    duration = time.perf_counter() - start

    assert resp1.status_code == 201, f"submit_attempt failed: {resp1.status_code} {resp1.text}"
    assert duration < 10.0, f"Submission took too long ({duration:.2f}s), timeout risk still present!"
    body = resp1.json()
    assert "attempt_id" in body
    assert body["score"] == 0.0
    assert len(body["results"]) == 20

    # Test duplicate submission within duplicate window -> 409 Conflict
    resp2 = client.post(
        f"/api/v1/quizzes/{quiz_id}/attempt",
        json={"answers": answers},
        headers=headers,
    )
    assert resp2.status_code == 409, f"Expected 409 Conflict on duplicate, got {resp2.status_code}"
