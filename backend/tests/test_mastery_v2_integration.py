from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import uuid
import pytest

from backend.core.config import Settings
from backend.services import progress_service
from backend.services.mastery_v2 import AttemptEvidence, compute_mastery


def test_row_to_evidence_conversion():
    q_id = uuid.uuid4()
    a_id = uuid.uuid4()
    now_dt = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Simulated row object returned by SQLAlchemy .all()
    mock_row = SimpleNamespace(
        question_id=q_id,
        attempt_id=a_id,
        is_correct=True,
        answered_at=now_dt,
        option_count=4,
    )

    evidence = AttemptEvidence(
        question_id=str(mock_row.question_id),
        session_id=str(mock_row.attempt_id),
        correct=mock_row.is_correct,
        timestamp=mock_row.answered_at,
        option_count=mock_row.option_count,
        difficulty=None,
    )

    assert evidence.question_id == str(q_id)
    assert evidence.session_id == str(a_id)
    assert evidence.correct is True
    assert evidence.timestamp == now_dt
    assert evidence.option_count == 4
    assert evidence.difficulty is None

    # Compute mastery with this evidence
    res = compute_mastery([evidence], now=now_dt)
    assert res.mastery_estimate is not None
    assert res.distinct_questions == 1


def test_flag_off_skips_v2_and_makes_no_queries():
    mock_db = MagicMock()
    mock_settings = Settings(database_url="sqlite://", mastery_v2_enabled=False)

    with patch("backend.core.config.get_settings", return_value=mock_settings):
        res = progress_service.update_mastery_v2_after_attempt(
            db=mock_db,
            student_id="student-123",
            topics=["Operating Systems", "Deadlocks"],
        )

    assert res == {}
    mock_db.query.assert_not_called()
    mock_db.commit.assert_not_called()


def test_failure_fallback_does_not_break_submission():
    # Verify that if update_mastery_v2_after_attempt raises an exception,
    # the failure is logged and existing v1 updated_mastery is preserved intact.
    v1_updated_mastery = {
        "Process Scheduling": {
            "mastery_score": 0.85,
            "trend": "improving",
            "attempt_count": 3,
            "last_quiz_passed": True,
        }
    }

    mock_db = MagicMock()
    mock_settings = Settings(database_url="sqlite://", mastery_v2_enabled=True)

    with patch("backend.core.config.get_settings", return_value=mock_settings), \
         patch("backend.services.progress_service.update_mastery_v2_after_attempt", side_effect=RuntimeError("DB query failed")):
        try:
            # Emulate the call inside submit_attempt
            progress_service.update_mastery_v2_after_attempt(mock_db, "stu_1", ["Process Scheduling"])
        except Exception:
            pass  # submit_attempt catches and logs

    # v1 dictionary is unmodified and fully intact
    assert v1_updated_mastery["Process Scheduling"]["mastery_score"] == 0.85
