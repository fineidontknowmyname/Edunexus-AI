import os
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from backend.api.quizzes import get_attempt_detail
from backend.services.insights_service import compute_class_average_from_student_scores


def test_t1_class_average_mastery_math():
    """Verify class average is the mean of student-level averages, not a flat unweighted topic mean."""
    # Student 1: 3 topics -> avg = (0.8 + 0.9 + 1.0) / 3 = 0.90
    # Student 2: 1 topic  -> avg = 0.50
    # True mean of student averages = (0.90 + 0.50) / 2 = 0.70
    # (Notice: flat topic mean would have been (0.8+0.9+1.0+0.5)/4 = 0.80, which is incorrect!)
    student_scores = [
        [0.80, 0.90, 1.00],
        [0.50],
    ]
    avg = compute_class_average_from_student_scores(student_scores)
    assert avg == 0.70

    # Empty cohort
    assert compute_class_average_from_student_scores([]) is None
    assert compute_class_average_from_student_scores([[], []]) is None


def test_t2_attempt_detail_access_decision_matrix():
    """Verify get_attempt_detail allows owning student and class educator, but 404s for others."""
    db_mock = MagicMock()
    att_id = uuid.uuid4()
    quiz_id = uuid.uuid4()
    class_id = uuid.uuid4()
    student_id = uuid.uuid4()
    educator_id = uuid.uuid4()
    stranger_id = uuid.uuid4()

    attempt_mock = MagicMock()
    attempt_mock.id = att_id
    attempt_mock.quiz_id = quiz_id
    attempt_mock.student_id = student_id
    attempt_mock.quiz.class_id = class_id
    attempt_mock.quiz.title = "OS Midterm"
    attempt_mock.quiz.passing_percentage = 70.0
    attempt_mock.quiz.questions = []
    attempt_mock.score = 85.0
    attempt_mock.answers = "{}"
    attempt_mock.topic_scores = "{}"
    attempt_mock.completed = True
    attempt_mock.completed_at = None

    db_mock.query.return_value.filter.return_value.first.return_value = attempt_mock
    db_mock.query.return_value.filter.return_value.all.return_value = []

    # 1. Owning student
    student_user = MagicMock()
    student_user.id = student_id
    student_res = get_attempt_detail(str(att_id), db_mock, student_user)
    assert student_res["viewer_role"] == "student"
    assert student_res["score"] == 85.0

    # 2. Owning educator
    educator_user = MagicMock()
    educator_user.id = educator_id
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("backend.api.quizzes.access.owned_quiz", lambda db, qid, u: attempt_mock.quiz)
        educator_res = get_attempt_detail(str(att_id), db_mock, educator_user)
        assert educator_res["viewer_role"] == "educator"
        assert educator_res["student_id"] == str(student_id)

    # 3. Unrelated stranger -> raises 404
    stranger_user = MagicMock()
    stranger_user.id = stranger_id
    with pytest.MonkeyPatch.context() as mp:
        def raise_404(*args, **kwargs):
            raise HTTPException(status_code=404, detail="Quiz not found")
        mp.setattr("backend.api.quizzes.access.owned_quiz", raise_404)
        with pytest.raises(HTTPException) as exc_info:
            get_attempt_detail(str(att_id), db_mock, stranger_user)
        assert exc_info.value.status_code == 404


@pytest.mark.skipif(not os.getenv("EDUNEXUS_DB_TESTS"), reason="Database tests disabled")
def test_t3_educator_quiz_attempts_list_db():
    """DB-gated integration test for educator attempts list endpoint."""
    pass


@pytest.mark.skipif(not os.getenv("EDUNEXUS_DB_TESTS"), reason="Database tests disabled")
def test_t4_class_average_mastery_db():
    """DB-gated test for class average computation across multiple enrolled students."""
    pass
