import asyncio
import inspect
import json
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException

from backend.api.quizzes import _claim_submission, submit_attempt
from backend.models import schemas
from backend.models.db import (
    Class,
    ClassEnrollment,
    Engagement,
    Quiz,
    QuizAttempt,
    QuizAttemptAnswer,
    QuizQuestion,
    ReviewStatus,
    TopicMastery,
    User,
    UserRole,
)
from backend.services import (
    evidence_service,
    misconception_service,
    progress_service,
    quiz_service,
    recommendation_service,
)

DB_TEST_REASON = (
    "Database-backed integration test skipped by default. "
    "Run only against a confirmed disposable Neon database branch by setting EDUNEXUS_DB_TESTS=1."
)


# ==============================================================================
# T1: Source code inspection asserting no internal commits in changed services
# ==============================================================================


def test_t1_no_db_commit_in_changed_services():
    """T1 (No DB): Assert that none of the submission pipeline services contain db.commit()."""
    changed_funcs = [
        _claim_submission,
        misconception_service.record_misconception,
        misconception_service.resolve_misconceptions_for_topic,
        progress_service.update_mastery_after_attempt,
        progress_service.update_mastery_v2_after_attempt,
        evidence_service.update_engagement,
        recommendation_service.link_quiz_attempt_to_recommendations,
    ]

    for func in changed_funcs:
        src = inspect.getsource(func)
        assert (
            "db.commit(" not in src
        ), f"{func.__name__} in {func.__module__} contains 'db.commit('; services must only flush() in unified transaction."


# ==============================================================================
# T2: Mocked session atomicity: exactly one commit on success, rollback on failure
# ==============================================================================


def test_t2_atomic_submission_commit_and_rollback():
    """T2 (No DB): submit_attempt commits exactly once on success and rolls back on failure."""

    async def _run():
        student_id = uuid.uuid4()
        quiz_id = uuid.uuid4()
        class_id = uuid.uuid4()
        user = User(id=student_id, role=UserRole.student)
        q1 = QuizQuestion(id=uuid.uuid4(), points=1.0)
        quiz = Quiz(
            id=quiz_id,
            title="Atomicity Test Quiz",
            status=ReviewStatus.approved,
            class_id=class_id,
            version=1,
            passing_percentage=60.0,
            questions=[q1],
        )
        payload = schemas.QuizAttemptCreate(answers={str(q1.id): "Option A"})
        attempt_id = uuid.uuid4()
        attempt = QuizAttempt(
            id=attempt_id,
            student_id=student_id,
            quiz_id=quiz.id,
            quiz_version=1,
        )

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.with_for_update.return_value.one.return_value = user
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.get.return_value = attempt

        score_result = {
            "score": 100.0,
            "topic_scores": {"OS": 1.0},
            "results": [
                {
                    "question_id": str(q1.id),
                    "correct": True,
                    "earned_points": 1.0,
                    "points_possible": 1.0,
                    "topic": "OS",
                }
            ],
            "ai_candidates": [],
        }

        with patch("backend.api.access.enrolled_quiz", return_value=quiz), patch(
            "backend.services.quiz_service.score_attempt", new=AsyncMock(return_value=score_result)
        ), patch(
            "backend.services.progress_service.update_mastery_after_attempt",
            return_value={"OS": {"mastery_score": 1.0}},
        ), patch(
            "backend.services.evidence_service.update_engagement"
        ) as mock_eng, patch(
            "backend.services.recommendation_service.link_quiz_attempt_to_recommendations", return_value=0
        ):
            # 1. Success case: exactly ONE commit, ZERO rollbacks
            bg = BackgroundTasks()
            res = await submit_attempt(str(quiz_id), payload, mock_db, user, None, bg)
            assert res["score"] == 100.0
            assert res["score_ratio"] == 1.0
            assert mock_db.commit.call_count == 1
            assert mock_db.rollback.call_count == 0

            # 2. Failure case: service raises exception -> rollback called, ZERO commits, 500 raised
            mock_db.reset_mock()
            mock_eng.side_effect = RuntimeError("Simulated network drop during engagement update")

            with pytest.raises(HTTPException) as exc_info:
                await submit_attempt(str(quiz_id), payload, mock_db, user, None, bg)

            assert exc_info.value.status_code == 500
            assert "Quiz scoring or saving failed" in exc_info.value.detail
            assert mock_db.commit.call_count == 0
            assert mock_db.rollback.call_count >= 1

    asyncio.run(_run())


# ==============================================================================
# T3 - T5: Database-backed tests (skipped unless EDUNEXUS_DB_TESTS=1)
# ==============================================================================


@pytest.mark.skipif(os.getenv("EDUNEXUS_DB_TESTS") != "1", reason=DB_TEST_REASON)
def test_t3_fault_injection_rollback_leaves_db_clean(client, db, student_user, sample_class):
    """T3 (Needs DB): Exception midway through submission rolls back everything."""
    # Setup approved quiz with 1 question
    quiz = Quiz(
        title="Fault Injection Quiz",
        class_id=sample_class.id,
        created_by_id=sample_class.educator_id,
        status=ReviewStatus.approved,
        version=1,
    )
    db.add(quiz)
    db.commit()
    db.refresh(quiz)

    q = QuizQuestion(
        quiz_id=quiz.id,
        question_text="Sample Q",
        options=json.dumps(["A", "B"]),
        correct_answer="A",
        points=1.0,
        topic="Fault Tolerant Systems",
    )
    db.add(q)
    enrollment = ClassEnrollment(class_id=sample_class.id, student_id=student_user.id)
    db.add(enrollment)
    db.commit()

    initial_attempts = db.query(QuizAttempt).filter(QuizAttempt.student_id == student_user.id).count()
    initial_answers = db.query(QuizAttemptAnswer).filter(QuizAttemptAnswer.student_id == student_user.id).count()

    from backend.core.security import create_access_token

    token = create_access_token(student_user.id, UserRole.student.value)
    headers = {"Authorization": f"Bearer {token}"}

    with patch("backend.services.evidence_service.update_engagement", side_effect=RuntimeError("Fault Injection")):
        resp = client.post(
            f"/quizzes/{quiz.id}/attempt",
            json={"answers": {str(q.id): "A"}},
            headers=headers,
        )
        assert resp.status_code == 500

    # Verify zero orphaned attempt rows, zero answers, and zero topic mastery
    current_attempts = db.query(QuizAttempt).filter(QuizAttempt.student_id == student_user.id).count()
    current_answers = db.query(QuizAttemptAnswer).filter(QuizAttemptAnswer.student_id == student_user.id).count()
    mastery_count = db.query(TopicMastery).filter(TopicMastery.student_id == student_user.id).count()

    assert current_attempts == initial_attempts
    assert current_answers == initial_answers
    assert mastery_count == 0


@pytest.mark.skipif(os.getenv("EDUNEXUS_DB_TESTS") != "1", reason=DB_TEST_REASON)
def test_t4_happy_path_atomic_submission(client, db, student_user, sample_class):
    """T4 (Needs DB): Happy path submission commits attempt, answers, mastery and engagement together."""
    quiz = Quiz(
        title="Happy Path Quiz",
        class_id=sample_class.id,
        created_by_id=sample_class.educator_id,
        status=ReviewStatus.approved,
        version=1,
    )
    db.add(quiz)
    db.commit()
    db.refresh(quiz)

    q = QuizQuestion(
        quiz_id=quiz.id,
        question_text="Happy Q",
        options=json.dumps(["A", "B"]),
        correct_answer="A",
        points=2.0,
        topic="Deadlocks",
    )
    db.add(q)
    db.add(ClassEnrollment(class_id=sample_class.id, student_id=student_user.id))
    db.commit()

    from backend.core.security import create_access_token

    token = create_access_token(student_user.id, UserRole.student.value)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        f"/quizzes/{quiz.id}/attempt",
        json={"answers": {str(q.id): "A"}},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "attempt_id" in data
    assert data["score"] == 100.0
    assert data["score_ratio"] == 1.0

    # Verify persisted in database
    saved_attempt = db.query(QuizAttempt).filter(QuizAttempt.id == uuid.UUID(data["attempt_id"])).first()
    assert saved_attempt is not None
    assert saved_attempt.completed is True
    assert saved_attempt.score == 100.0

    answers = db.query(QuizAttemptAnswer).filter(QuizAttemptAnswer.attempt_id == saved_attempt.id).all()
    assert len(answers) == 1
    assert answers[0].points_awarded == 2.0

    mastery = db.query(TopicMastery).filter(
        TopicMastery.student_id == student_user.id, TopicMastery.topic == "Deadlocks"
    ).first()
    assert mastery is not None
    assert mastery.mastery_score == 1.0


@pytest.mark.skipif(os.getenv("EDUNEXUS_DB_TESTS") != "1", reason=DB_TEST_REASON)
def test_t5_simultaneous_or_window_duplicate_returns_409(client, db, student_user, sample_class):
    """T5 (Needs DB): Second submission with identical answers within 30s window returns 409."""
    quiz = Quiz(
        title="Duplicate Test Quiz",
        class_id=sample_class.id,
        created_by_id=sample_class.educator_id,
        status=ReviewStatus.approved,
        version=1,
    )
    db.add(quiz)
    db.commit()
    db.refresh(quiz)

    q = QuizQuestion(
        quiz_id=quiz.id,
        question_text="Dup Q",
        options=json.dumps(["A", "B"]),
        correct_answer="A",
        points=1.0,
        topic="Concurrency",
    )
    db.add(q)
    db.add(ClassEnrollment(class_id=sample_class.id, student_id=student_user.id))
    db.commit()

    from backend.core.security import create_access_token

    token = create_access_token(student_user.id, UserRole.student.value)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {"answers": {str(q.id): "A"}}

    # First submission -> 201
    resp1 = client.post(f"/quizzes/{quiz.id}/attempt", json=payload, headers=headers)
    assert resp1.status_code == 201

    # Second immediate submission -> 409 Conflict
    resp2 = client.post(f"/quizzes/{quiz.id}/attempt", json=payload, headers=headers)
    assert resp2.status_code == 409
    assert "already received" in resp2.json()["detail"]
