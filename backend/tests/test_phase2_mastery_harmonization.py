"""Tests for Phase 2: Mastery classification and threshold harmonization."""

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from backend.core.tracking_constants import (
    MASTERED_THRESHOLD,
    WEAK_THRESHOLD,
    URGENT_THRESHOLD,
    classify_topic,
)
from backend.models.db import (
    Class,
    Document,
    MasteryTrend,
    PrerequisiteMap,
    Quiz,
    QuizAttempt,
    Subject,
    TopicMastery,
    User,
    UserRole,
)
from backend.services import progress_service, recommendation_service


def test_classify_topic_grid():
    # 1. Zero attempts or insufficient evidence -> 'insufficient'
    assert classify_topic(0, "none", "unknown", 0.0) == "insufficient"
    assert classify_topic(0, "sufficient", "high", 0.9) == "insufficient"
    assert classify_topic(3, "insufficient", "low", 0.3) == "insufficient"
    assert classify_topic(3, "none", "medium", 0.65) == "insufficient"
    assert classify_topic(2, None, None, 0.5) == "insufficient"

    # 2. V2 band present with sufficient / direct evidence -> uses band
    assert classify_topic(3, "sufficient", "low", 0.35) == "weak"
    assert classify_topic(3, "direct", "low", 0.35) == "weak"
    assert classify_topic(3, "sufficient", "medium", 0.65) == "developing"
    assert classify_topic(3, "direct", "medium", 0.65) == "developing"
    assert classify_topic(4, "sufficient", "high", 0.85) == "strong"
    assert classify_topic(4, "direct", "high", 0.85) == "strong"

    # 3. Fallback to V1 score when V2 band is absent or unknown
    # score < 0.60 -> weak
    assert classify_topic(3, "sufficient", None, 0.59) == "weak"
    assert classify_topic(3, "sufficient", "unknown", 0.0) == "weak"
    assert classify_topic(3, "sufficient", "", 0.40) == "weak"
    # 0.60 <= score < 0.70 -> developing
    assert classify_topic(3, "sufficient", None, 0.60) == "developing"
    assert classify_topic(3, "sufficient", None, 0.65) == "developing"
    assert classify_topic(3, "sufficient", None, 0.6999) == "developing"
    # score >= 0.70 -> strong
    assert classify_topic(3, "sufficient", None, 0.70) == "strong"
    assert classify_topic(3, "sufficient", None, 0.85) == "strong"


def test_medium_band_get_recommendation_reinforce():
    db = MagicMock()
    student_id = str(uuid.uuid4())
    class_id = str(uuid.uuid4())
    topic = "Concurrency Control"

    # Topic with score 0.65, band medium, sufficient evidence
    mock_mastery = TopicMastery(
        student_id=uuid.UUID(student_id),
        class_id=uuid.UUID(class_id),
        topic=topic,
        mastery_score=0.65,
        attempt_count=3,
        trend=MasteryTrend.stable,
        mastery_v2=json.dumps({"mastery_band": "medium", "evidence_state": "sufficient", "accuracy": 0.65}),
    )

    def mock_query(*args):
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        q.filter.return_value.all.return_value = []
        if args and args[0] is TopicMastery:
            q.filter.return_value.first.return_value = mock_mastery
            q.filter.return_value.all.return_value = [mock_mastery]
        return q

    db.query.side_effect = mock_query
    mock_class = Class(id=uuid.UUID(class_id), name="DB Systems", subject_id=uuid.uuid4(), subject="Databases")
    db.get.return_value = mock_class

    with patch("backend.services.recommendation_service._library_resources", return_value=([], [])), \
         patch("backend.services.recommendation_service._curriculum_sections", return_value=[]), \
         patch("backend.services.recommendation_service._check_prerequisite_gap", return_value=None), \
         patch("backend.services.behavior_service.get_learning_tag", return_value=None), \
         patch("backend.services.routing_service.get_topic_routing", return_value="normal"):
        rec = recommendation_service.get_recommendation(
            db, student_id, class_id, str(mock_class.subject_id), topic, embedding_model=None
        )

    assert rec["mode"] == "reinforce"
    assert "haven't attempted" not in rec["reason"].lower()


def test_medium_band_progress_recommendations_developing_topics():
    db = MagicMock()
    student_id = str(uuid.uuid4())
    class_id = str(uuid.uuid4())
    subject_id = uuid.uuid4()

    mock_class = Class(id=uuid.UUID(class_id), name="DB Systems", subject_id=subject_id, subject="Databases")
    mock_subject = Subject(id=subject_id, name="Databases")

    mock_syllabus = [
        PrerequisiteMap(id=uuid.uuid4(), subject_id=subject_id, topic="Concurrency Control"),
    ]

    mock_mastery = TopicMastery(
        student_id=uuid.UUID(student_id),
        class_id=uuid.UUID(class_id),
        topic="Concurrency Control",
        mastery_score=0.65,
        attempt_count=3,
        trend=MasteryTrend.stable,
        mastery_v2=json.dumps({"mastery_band": "medium", "evidence_state": "sufficient", "accuracy": 0.65}),
    )

    def mock_get(entity, ident):
        if entity == Class:
            return mock_class
        if entity == Subject:
            return mock_subject
        return None

    def mock_query(*entities, **kwargs):
        q = MagicMock()
        q.join.return_value = q
        q.filter.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q
        if len(entities) == 1:
            if entities[0] == TopicMastery:
                q.all.return_value = [mock_mastery]
            elif entities[0] == PrerequisiteMap:
                q.all.return_value = mock_syllabus
            else:
                q.all.return_value = []
        else:
            q.all.return_value = []
        return q

    db.get.side_effect = mock_get
    db.query.side_effect = mock_query

    with patch("backend.services.recommendation_service._library_resources", return_value=([], [])), \
         patch("backend.services.youtube_service.discover_topic_videos", return_value=[]):
        res = recommendation_service.get_progress_recommendations(db, student_id=student_id, class_id=class_id)

    # Must be in developing_topics, NOT empty and NOT all_topics_strong
    dev_names = [d["topic"] for d in res.get("developing_topics", [])]
    assert "Concurrency Control" in dev_names
    assert res["all_topics_strong"] is False


def test_mastered_topics_threshold_matches_70_percent():
    scores = [0.35, 0.65, 0.70, 0.72, 0.74, 0.85]
    # Under MASTERED_THRESHOLD = 0.70:
    # 0.70, 0.72, 0.74, 0.85 are all >= 0.70 -> exactly 4 topics!
    summary = progress_service.compute_dashboard_summary(scores, syllabus_topics=10)
    assert summary["mastered_topics"] == 4


def test_topic_score_history_normalization():
    db = MagicMock()
    student_id = str(uuid.uuid4())
    class_id = str(uuid.uuid4())

    att1 = MagicMock()
    att1.topic_scores = json.dumps({"Deadlocks ": 0.75})
    att2 = MagicMock()
    att2.topic_scores = json.dumps({"deadlocks": 0.85})
    att3 = MagicMock()
    att3.topic_scores = json.dumps({"Deadlocks": 0.90})

    db.query.return_value.join.return_value.filter.return_value.order_by.return_value.all.return_value = [att1, att2, att3]

    scores = progress_service._topic_score_history(db, student_id, class_id, "Deadlocks")
    assert scores == [0.75, 0.85, 0.90]
