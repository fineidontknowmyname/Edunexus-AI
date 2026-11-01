import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import BackgroundTasks, HTTPException

from backend.api.quizzes import submit_attempt
from backend.models import schemas
from backend.models.db import ReviewStatus, UserRole


@pytest.fixture
def mock_quiz():
    q1_id = uuid.uuid4()
    q2_id = uuid.uuid4()
    q1 = MagicMock(id=q1_id)
    q2 = MagicMock(id=q2_id)
    quiz = MagicMock(
        id=uuid.uuid4(),
        class_id=uuid.uuid4(),
        status=ReviewStatus.approved,
        questions=[q1, q2],
    )
    return quiz, [q1_id, q2_id]


@pytest.fixture
def mock_student():
    student = MagicMock()
    student.id = uuid.uuid4()
    student.role = UserRole.student
    return student


@pytest.mark.anyio
async def test_submit_attempt_rejects_empty_dict(mock_quiz, mock_student):
    quiz, _ = mock_quiz
    db = MagicMock()
    background_tasks = BackgroundTasks()
    payload = schemas.QuizAttemptCreate(answers={})

    with patch("backend.api.quizzes.access.enrolled_quiz", return_value=quiz), \
         patch("backend.api.quizzes._claim_submission") as mock_claim:
        with pytest.raises(HTTPException) as exc_info:
            await submit_attempt(
                quiz_id=str(quiz.id),
                payload=payload,
                db=db,
                current_user=mock_student,
                _student=None,
                background_tasks=background_tasks,
            )
        assert exc_info.value.status_code == 400
        assert "Answer at least one question before submitting" in exc_info.value.detail
        mock_claim.assert_not_called()


@pytest.mark.anyio
async def test_submit_attempt_rejects_all_blank_values(mock_quiz, mock_student):
    quiz, [q1_id, q2_id] = mock_quiz
    db = MagicMock()
    background_tasks = BackgroundTasks()
    payload = schemas.QuizAttemptCreate(answers={str(q1_id): "", str(q2_id): None})

    with patch("backend.api.quizzes.access.enrolled_quiz", return_value=quiz), \
         patch("backend.api.quizzes._claim_submission") as mock_claim:
        with pytest.raises(HTTPException) as exc_info:
            await submit_attempt(
                quiz_id=str(quiz.id),
                payload=payload,
                db=db,
                current_user=mock_student,
                _student=None,
                background_tasks=background_tasks,
            )
        assert exc_info.value.status_code == 400
        assert "Answer at least one question before submitting" in exc_info.value.detail
        mock_claim.assert_not_called()


@pytest.mark.anyio
async def test_submit_attempt_accepts_one_answered_question(mock_quiz, mock_student):
    quiz, [q1_id, q2_id] = mock_quiz
    db = MagicMock()
    background_tasks = BackgroundTasks()
    # Partially answered: q1 answered, q2 omitted
    payload = schemas.QuizAttemptCreate(answers={str(q1_id): "Option A"})

    mock_attempt = MagicMock(id=uuid.uuid4())
    db.get.return_value = mock_attempt

    score_result = {
        "score": 100.0,
        "total_earned_points": 2.0,
        "total_max_points": 2.0,
        "topic_scores": {"Topic 1": 1.0},
        "topic_passed": {"Topic 1": True},
        "results": [
            {"question_id": str(q1_id), "correct": True, "earned_points": 2.0, "points_possible": 2.0}
        ],
        "ai_candidates": [],
    }

    with patch("backend.api.quizzes.access.enrolled_quiz", return_value=quiz), \
         patch("backend.api.quizzes._claim_submission", return_value=mock_attempt) as mock_claim, \
         patch("backend.services.quiz_service.score_attempt", new=AsyncMock(return_value=score_result)), \
         patch("backend.services.progress_service.update_mastery_after_attempt", return_value={}), \
         patch("backend.services.evidence_service.update_engagement"), \
         patch("backend.services.quiz_service.build_answer_rows", return_value=[]):

        resp = await submit_attempt(
            quiz_id=str(quiz.id),
            payload=payload,
            db=db,
            current_user=mock_student,
            _student=None,
            background_tasks=background_tasks,
        )

        mock_claim.assert_called_once()
        assert resp["attempt_id"] == str(mock_attempt.id)
        assert resp["score"] == 100.0
        # Check attempt level points set on mock_attempt
        assert mock_attempt.points_earned == 2.0
        assert mock_attempt.max_points == 2.0
        assert mock_attempt.completed is True
