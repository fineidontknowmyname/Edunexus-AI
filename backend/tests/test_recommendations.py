import json
import uuid
from unittest.mock import MagicMock, patch
import pytest

from backend.core.config import Settings
from backend.models.db import (
    LearningResource,
    MasteryTrend,
    RecommendationLog,
    ResourceType,
    ReviewStatus,
    TopicMastery,
    User,
    UserRole,
)
from backend.services.recommendation_service import _check_prerequisite_gap, _library_resources, get_recommendation


@pytest.fixture
def base_db():
    mock_db = MagicMock()
    return mock_db


def test_recommendation_open_misconception_highest_priority(base_db):
    student_id = str(uuid.uuid4())
    class_id = str(uuid.uuid4())

    with patch("backend.services.routing_service.get_topic_routing", return_value="intervene"), \
         patch("backend.services.behavior_service.get_learning_tag", return_value=None), \
         patch("backend.services.recommendation_service._library_resources", return_value=([], [])):

        base_db.query.return_value.filter.return_value.first.return_value = None

        rec = get_recommendation(
            db=base_db,
            student_id=student_id,
            class_id=class_id,
            subject_id=None,
            topic="Deadlocks",
            embedding_model=None,
        )

    assert rec["mode"] == "ai_session"
    assert "open misconception" in rec["reason"]
    assert rec["socratic_seed_message"] == "Deadlocks"


def test_recommendation_prerequisite_gap_triggers_session(base_db):
    student_id = str(uuid.uuid4())
    class_id = str(uuid.uuid4())
    subject_id = str(uuid.uuid4())

    with patch("backend.services.routing_service.get_topic_routing", return_value="reinforce"), \
         patch("backend.services.behavior_service.get_learning_tag", return_value=None), \
         patch("backend.core.prerequisites.get_prerequisites_db", return_value=["Processes"]), \
         patch("backend.services.routing_service.intervene_topics", return_value={"Processes"}), \
         patch("backend.services.recommendation_service._library_resources", return_value=([], [])):

        base_db.query.return_value.filter.return_value.first.return_value = None

        rec = get_recommendation(
            db=base_db,
            student_id=student_id,
            class_id=class_id,
            subject_id=subject_id,
            topic="Deadlocks",
            embedding_model=None,
        )

    assert rec["mode"] == "ai_session"
    assert "Prerequisite 'Processes' has an unresolved misconception" in rec["reason"]


def test_recommendation_v2_decision_ladder(base_db):
    student_id = str(uuid.uuid4())
    class_id = str(uuid.uuid4())

    mock_settings = Settings(database_url="sqlite://", mastery_v2_enabled=True)

    cases = [
        # (band, evidence, expected_mode)
        ("low", "sufficient", "ai_session"),
        ("low", "insufficient", "diagnostic"),
        ("medium", "insufficient", "diagnostic"),
        ("high", "insufficient", "verification"),
        ("high", "sufficient", "advance"),
        ("unknown", "none", "initial_assessment"),
    ]

    for band, evidence, expected_mode in cases:
        v2_payload = json.dumps({
            "mastery_band": band,
            "evidence_state": evidence,
            "mastery_estimate": 0.8 if band == "high" else 0.3,
            "trend": "stable",
        })

        mock_mastery = TopicMastery(
            student_id=student_id,
            class_id=class_id,
            topic="CPU Scheduling",
            mastery_v2=v2_payload,
        )
        base_db.query.return_value.filter.return_value.first.return_value = mock_mastery

        with patch("backend.core.config.get_settings", return_value=mock_settings), \
             patch("backend.services.routing_service.get_topic_routing", return_value="reinforce"), \
             patch("backend.services.behavior_service.get_learning_tag", return_value=None), \
             patch("backend.services.recommendation_service._check_prerequisite_gap", return_value=None), \
             patch("backend.services.recommendation_service._library_resources", return_value=([], [])):

            rec = get_recommendation(
                db=base_db,
                student_id=student_id,
                class_id=class_id,
                subject_id=None,
                topic="CPU Scheduling",
                embedding_model=None,
            )

        assert rec["mode"] == expected_mode, f"Failed for band={band}, evidence={evidence}"


def test_recommendation_fallback_to_v1_stalled(base_db):
    student_id = str(uuid.uuid4())
    class_id = str(uuid.uuid4())

    mock_settings = Settings(database_url="sqlite://", mastery_v2_enabled=False)
    mock_mastery = TopicMastery(
        student_id=student_id,
        class_id=class_id,
        topic="Paging",
        attempt_count=3,
        mastery_score=0.45,
        trend=MasteryTrend.declining,
        mastery_v2=None,
    )
    base_db.query.return_value.filter.return_value.first.return_value = mock_mastery

    with patch("backend.core.config.get_settings", return_value=mock_settings), \
         patch("backend.services.routing_service.get_topic_routing", return_value="reinforce"), \
         patch("backend.services.behavior_service.get_learning_tag", return_value=None), \
         patch("backend.services.recommendation_service._check_prerequisite_gap", return_value=None), \
         patch("backend.services.recommendation_service._library_resources", return_value=([], [])):

        rec = get_recommendation(
            db=base_db,
            student_id=student_id,
            class_id=class_id,
            subject_id=None,
            topic="Paging",
            embedding_model=None,
        )

    assert rec["mode"] == "ai_session"
    assert "scores on this topic haven't moved" in rec["reason"]


def test_library_resources_ranking(base_db):
    class_id = str(uuid.uuid4())
    topic = "Process Synchronization"

    # Faculty resource (lower helpful count)
    r1 = LearningResource(
        id=uuid.uuid4(),
        topic=topic,
        title="Professor's Peterson Solution Video",
        resource_type=ResourceType.youtube,
        url="https://youtube.com/watch?v=11111111111",
        helpful_count=1,
    )
    # Student resource (higher helpful count)
    r2 = LearningResource(
        id=uuid.uuid4(),
        topic=topic,
        title="Student Cheatsheet Notes",
        resource_type=ResourceType.notes,
        content="Mutex vs Semaphore summary",
        helpful_count=10,
    )

    # Mock DB query returning (resource, role)
    base_db.query.return_value.join.return_value.filter.return_value.order_by.return_value.all.return_value = [
        (r1, UserRole.educator),
        (r2, UserRole.student),
    ]

    videos, notes = _library_resources(base_db, class_id, topic)

    assert len(videos) == 1
    assert videos[0]["title"] == "Professor's Peterson Solution Video"
    assert videos[0]["channel"] == "Faculty Approved"

    assert len(notes) == 1
    assert notes[0]["title"] == "Student Cheatsheet Notes"
    assert notes[0]["author_role"] == "student"
    assert notes[0]["content"] == "Mutex vs Semaphore summary"
    assert notes[0]["content_length"] == len("Mutex vs Semaphore summary")
    assert notes[0]["truncated"] is False


def test_library_resources_notes_truncation(base_db):
    class_id = str(uuid.uuid4())
    topic = "Process Synchronization"

    long_note = LearningResource(
        id=uuid.uuid4(),
        topic=topic,
        title="Very Long Note",
        resource_type=ResourceType.notes,
        content="N" * 600,
        helpful_count=5,
    )

    base_db.query.return_value.join.return_value.filter.return_value.order_by.return_value.all.return_value = [
        (long_note, UserRole.student),
    ]

    videos, notes = _library_resources(base_db, class_id, topic)

    assert len(notes) == 1
    assert notes[0]["content"] == "N" * 500
    assert notes[0]["content_length"] == 600
    assert notes[0]["truncated"] is True


def test_recommendation_outcome_tracking_linkage(base_db):
    from backend.models.db import RecommendationLog
    from backend.services.recommendation_service import link_quiz_attempt_to_recommendations

    student_id = str(uuid.uuid4())
    class_id = str(uuid.uuid4())
    attempt_id = str(uuid.uuid4())

    rec_log = RecommendationLog(
        id=uuid.uuid4(),
        student_id=student_id,
        class_id=class_id,
        topic="Deadlocks",
        mode="diagnostic",
        outcome_score_before=0.4,
        outcome_attempt_id=None,
    )

    base_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = rec_log

    linked = link_quiz_attempt_to_recommendations(
        db=base_db,
        student_id=student_id,
        class_id=class_id,
        attempt_id=attempt_id,
        topic_scores={"Deadlocks": 0.85},
        updated_mastery={"Deadlocks": {"mastery_score": 0.85}},
    )

    assert linked == 1
    assert rec_log.outcome_attempt_id == attempt_id
    assert rec_log.outcome_score_after == 0.85
    assert rec_log.outcome_delta == 0.45
    base_db.commit.assert_called_once()


def test_recommendation_outcome_missing_updated_mastery_skips_linking(base_db):
    from backend.models.db import RecommendationLog
    from backend.services.recommendation_service import link_quiz_attempt_to_recommendations

    student_id = str(uuid.uuid4())
    class_id = str(uuid.uuid4())
    attempt_id = str(uuid.uuid4())

    rec_log = RecommendationLog(
        id=uuid.uuid4(),
        student_id=student_id,
        class_id=class_id,
        topic="Deadlocks",
        mode="diagnostic",
        outcome_score_before=0.4,
        outcome_attempt_id=None,
    )

    base_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = rec_log

    # When updated_mastery is None or lacks topic mastery_score
    linked = link_quiz_attempt_to_recommendations(
        db=base_db,
        student_id=student_id,
        class_id=class_id,
        attempt_id=attempt_id,
        topic_scores={"Deadlocks": 0.85},
        updated_mastery=None,
    )

    assert linked == 0
    assert rec_log.outcome_attempt_id is None
    assert rec_log.outcome_score_after is None
    assert rec_log.outcome_delta is None


def test_recommendation_outcome_missing_before_leaves_delta_none(base_db):
    from backend.models.db import RecommendationLog
    from backend.services.recommendation_service import link_quiz_attempt_to_recommendations

    student_id = str(uuid.uuid4())
    class_id = str(uuid.uuid4())
    attempt_id = str(uuid.uuid4())

    rec_log = RecommendationLog(
        id=uuid.uuid4(),
        student_id=student_id,
        class_id=class_id,
        topic="Deadlocks",
        mode="diagnostic",
        outcome_score_before=None,  # No prior mastery recorded
        outcome_attempt_id=None,
    )

    base_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = rec_log

    linked = link_quiz_attempt_to_recommendations(
        db=base_db,
        student_id=student_id,
        class_id=class_id,
        attempt_id=attempt_id,
        topic_scores={"Deadlocks": 0.85},
        updated_mastery={"Deadlocks": {"mastery_score": 0.85}},
    )

    assert linked == 1
    assert rec_log.outcome_attempt_id == attempt_id
    assert rec_log.outcome_score_after == 0.85
    assert rec_log.outcome_delta is None
    base_db.commit.assert_called_once()


def test_recommendation_outcome_uses_updated_mastery_v1(base_db):
    from backend.models.db import RecommendationLog
    from backend.services.recommendation_service import link_quiz_attempt_to_recommendations

    student_id = str(uuid.uuid4())
    class_id = str(uuid.uuid4())
    attempt_id = str(uuid.uuid4())

    rec_log = RecommendationLog(
        id=uuid.uuid4(),
        student_id=student_id,
        class_id=class_id,
        topic="Deadlocks",
        mode="ai_session",
        outcome_score_before=0.40,
        outcome_attempt_id=None,
    )

    base_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = rec_log

    updated_mastery = {
        "Deadlocks": {
            "mastery_score": 0.72,
            "trend": "improving",
            "attempt_count": 3,
        }
    }

    linked = link_quiz_attempt_to_recommendations(
        db=base_db,
        student_id=student_id,
        class_id=class_id,
        attempt_id=attempt_id,
        topic_scores={"Deadlocks": 1.0},  # Raw quiz score was 100%
        updated_mastery=updated_mastery,
    )

    assert linked == 1
    assert rec_log.outcome_attempt_id == attempt_id
    # Outcome score after must be the v1 mastery score (0.72), NOT the raw quiz score (1.0)
    assert rec_log.outcome_score_after == 0.72
    assert rec_log.outcome_delta == 0.32
    base_db.commit.assert_called_once()


def _make_dedup_db(existing_log=None):
    mock_db = MagicMock()
    def query_side_effect(model):
        q = MagicMock()
        if model is TopicMastery:
            q.filter.return_value.first.return_value = None
        elif model is RecommendationLog:
            q.filter.return_value.order_by.return_value.first.return_value = existing_log
        return q
    mock_db.query.side_effect = query_side_effect
    return mock_db


def test_recommendation_deduplication_within_24h_does_not_insert():
    student_id = str(uuid.uuid4())
    class_id = str(uuid.uuid4())
    existing_id = uuid.uuid4()
    from datetime import datetime, timezone
    from backend.models.db import RecommendationLog

    existing_log = RecommendationLog(
        id=existing_id,
        student_id=student_id,
        class_id=class_id,
        topic="Deadlocks",
        mode="ai_session",
        reason="Existing reason",
        outcome_attempt_id=None,
        created_at=datetime.now(timezone.utc),
    )

    db = _make_dedup_db(existing_log=existing_log)

    with patch("backend.services.routing_service.get_topic_routing", return_value="intervene"), \
         patch("backend.services.behavior_service.get_learning_tag", return_value=None), \
         patch("backend.services.recommendation_service._library_resources", return_value=([], [])):

        rec = get_recommendation(
            db=db,
            student_id=student_id,
            class_id=class_id,
            subject_id=None,
            topic="Deadlocks",
            embedding_model=None,
        )

    assert rec["id"] == str(existing_id)
    db.add.assert_not_called()


def test_recommendation_deduplication_different_mode_inserts():
    # When existing log had mode="static" but new recommendation has mode="ai_session", query returns None
    student_id = str(uuid.uuid4())
    class_id = str(uuid.uuid4())

    db = _make_dedup_db(existing_log=None)

    with patch("backend.services.routing_service.get_topic_routing", return_value="intervene"), \
         patch("backend.services.behavior_service.get_learning_tag", return_value=None), \
         patch("backend.services.recommendation_service._library_resources", return_value=([], [])):

        rec = get_recommendation(
            db=db,
            student_id=student_id,
            class_id=class_id,
            subject_id=None,
            topic="Deadlocks",
            embedding_model=None,
        )

    db.add.assert_called_once()
    added_obj = db.add.call_args[0][0]
    assert added_obj.mode == "ai_session"
    assert rec["mode"] == "ai_session"


def test_recommendation_deduplication_older_than_24h_inserts():
    # If the unlinked row was created >24h ago, filter on created_at >= cutoff yields None -> new insert
    student_id = str(uuid.uuid4())
    class_id = str(uuid.uuid4())

    db = _make_dedup_db(existing_log=None)

    with patch("backend.services.routing_service.get_topic_routing", return_value="intervene"), \
         patch("backend.services.behavior_service.get_learning_tag", return_value=None), \
         patch("backend.services.recommendation_service._library_resources", return_value=([], [])):

        rec = get_recommendation(
            db=db,
            student_id=student_id,
            class_id=class_id,
            subject_id=None,
            topic="Deadlocks",
            embedding_model=None,
        )

    db.add.assert_called_once()


def test_recommendation_deduplication_already_linked_inserts():
    # If the row within 24h is already linked (outcome_attempt_id is not None), query filter outcome_attempt_id.is_(None) yields None -> new insert
    student_id = str(uuid.uuid4())
    class_id = str(uuid.uuid4())

    db = _make_dedup_db(existing_log=None)

    with patch("backend.services.routing_service.get_topic_routing", return_value="intervene"), \
         patch("backend.services.behavior_service.get_learning_tag", return_value=None), \
         patch("backend.services.recommendation_service._library_resources", return_value=([], [])):

        rec = get_recommendation(
            db=db,
            student_id=student_id,
            class_id=class_id,
            subject_id=None,
            topic="Deadlocks",
            embedding_model=None,
        )

    db.add.assert_called_once()


def test_recommendation_static_mode_does_not_log(base_db):
    student_id = str(uuid.uuid4())
    class_id = str(uuid.uuid4())

    mock_settings = Settings(database_url="sqlite://", mastery_v2_enabled=False)
    base_db.query.return_value.filter.return_value.first.return_value = None

    with patch("backend.core.config.get_settings", return_value=mock_settings), \
         patch("backend.services.routing_service.get_topic_routing", return_value="reinforce"), \
         patch("backend.services.behavior_service.get_learning_tag", return_value=None), \
         patch("backend.services.recommendation_service._check_prerequisite_gap", return_value=None), \
         patch("backend.services.recommendation_service._library_resources", return_value=([], [])):

        rec = get_recommendation(
            db=base_db,
            student_id=student_id,
            class_id=class_id,
            subject_id=None,
            topic="Operating Systems Intro",
            embedding_model=None,
        )

    assert rec["mode"] == "static"
    assert rec["id"] is None
    base_db.add.assert_not_called()
    for call_item in base_db.query.call_args_list:
        assert call_item[0][0] is not RecommendationLog

