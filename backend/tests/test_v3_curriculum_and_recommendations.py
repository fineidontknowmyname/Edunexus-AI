import json
import uuid
import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from backend.api.classes import get_class_curation_topics
from backend.api.resources import create_resource
from backend.models import schemas
from backend.models.db import (
    Class,
    LearningResource,
    MasteryTrend,
    PrerequisiteMap,
    Quiz,
    ResourceType,
    ReviewStatus,
    Subject,
    TopicMastery,
    User,
    UserRole,
)
from backend.services import recommendation_service, youtube_service


def test_curation_topics_approved_syllabus():
    db = MagicMock()
    class_id = uuid.uuid4()
    subject_id = uuid.uuid4()
    topic_id_1 = str(uuid.uuid4())
    topic_id_2 = str(uuid.uuid4())

    mock_class = Class(id=class_id, name="Big Data Analytics A", subject_id=subject_id, subject="Big Data Analytics")
    mock_subject = Subject(id=subject_id, name="Big Data Analytics")
    current_user = User(id=uuid.uuid4(), full_name="Dr. Smith", role=UserRole.educator)

    mock_topics = [
        PrerequisiteMap(id=uuid.UUID(topic_id_1), subject_id=subject_id, topic="HDFS Architecture", description="Distributed filesystem", requires=[], related_concepts=[]),
        PrerequisiteMap(id=uuid.UUID(topic_id_2), subject_id=subject_id, topic="Spark RDDs", description="Resilient distributed datasets", requires=["HDFS Architecture"], related_concepts=[]),
    ]

    db.get.return_value = mock_subject
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_topics

    with patch("backend.api.classes.access.user_class_access", return_value=mock_class):
        res = get_class_curation_topics(class_id=str(class_id), db=db, current_user=current_user)

    assert res["status"] == "approved"
    assert res["subject_name"] == "Big Data Analytics"
    assert len(res["topics"]) == 2
    assert res["topics"][0]["topic"] == "HDFS Architecture"
    assert res["topics"][0]["id"] == topic_id_1
    assert res["topics"][1]["topic"] == "Spark RDDs"
    # Ensure no Operating Systems topics leaked
    assert all("CPU" not in t["topic"] and "Process" not in t["topic"] for t in res["topics"])


def test_curation_topics_no_syllabus():
    db = MagicMock()
    class_id = uuid.uuid4()
    subject_id = uuid.uuid4()

    mock_class = Class(id=class_id, name="Quantum Computing 101", subject_id=subject_id, subject="Quantum Computing")
    mock_subject = Subject(id=subject_id, name="Quantum Computing")
    current_user = User(id=uuid.uuid4(), full_name="Dr. Smith", role=UserRole.educator)

    db.get.return_value = mock_subject
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

    with patch("backend.api.classes.access.user_class_access", return_value=mock_class):
        res = get_class_curation_topics(class_id=str(class_id), db=db, current_user=current_user)

    assert res["status"] == "no_syllabus"
    assert len(res["topics"]) == 0
    assert "upload and approve" in res["message"].lower()


def test_curation_topics_no_subject():
    db = MagicMock()
    class_id = uuid.uuid4()

    mock_class = Class(id=class_id, name="Independent Study", subject_id=None, subject=None)
    current_user = User(id=uuid.uuid4(), full_name="Dr. Smith", role=UserRole.educator)

    with patch("backend.api.classes.access.user_class_access", return_value=mock_class):
        res = get_class_curation_topics(class_id=str(class_id), db=db, current_user=current_user)

    assert res["status"] == "no_subject"
    assert len(res["topics"]) == 0


def test_curation_rejects_unapproved_topic():
    db = MagicMock()
    class_id = uuid.uuid4()
    subject_id = uuid.uuid4()

    mock_class = Class(id=class_id, name="Big Data Analytics A", subject_id=subject_id, subject="Big Data Analytics")
    current_user = User(id=uuid.uuid4(), full_name="Dr. Smith", role=UserRole.educator)

    mock_syllabus = [
        PrerequisiteMap(id=uuid.uuid4(), subject_id=subject_id, topic="HDFS Architecture"),
    ]
    db.query.return_value.filter.return_value.all.return_value = mock_syllabus

    payload = schemas.LearningResourceCreate(
        class_id=str(class_id),
        topic="CPU Scheduling",  # Unrelated topic
        title="Intro to CPU Scheduling",
        resource_type="youtube",
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    )

    with patch("backend.api.resources.access.user_class_access", return_value=mock_class):
        with pytest.raises(HTTPException) as exc_info:
            create_resource(payload=payload, db=db, current_user=current_user)

    assert exc_info.value.status_code == 400
    assert "not in the approved syllabus" in exc_info.value.detail


def test_curation_accepts_approved_topic():
    db = MagicMock()
    class_id = uuid.uuid4()
    subject_id = uuid.uuid4()
    topic_uuid = str(uuid.uuid4())

    mock_class = Class(id=class_id, name="Big Data Analytics A", subject_id=subject_id, subject="Big Data Analytics")
    current_user = User(id=uuid.uuid4(), full_name="Dr. Smith", role=UserRole.educator)

    mock_syllabus = [
        PrerequisiteMap(id=uuid.UUID(topic_uuid), subject_id=subject_id, topic="Spark RDDs"),
    ]
    db.query.return_value.filter.return_value.all.return_value = mock_syllabus

    payload = schemas.LearningResourceCreate(
        class_id=str(class_id),
        topic="Spark RDDs",
        topic_id=topic_uuid,
        title="Apache Spark RDD Tutorial",
        resource_type="youtube",
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    )

    with patch("backend.api.resources.access.user_class_access", return_value=mock_class):
        res = create_resource(payload=payload, db=db, current_user=current_user)

    assert res.topic == "Spark RDDs"
    assert res.status == "approved"
    assert res.topic_id == topic_uuid
    assert res.subject_id == str(subject_id)
    db.add.assert_called_once()
    db.commit.assert_called_once()


def test_youtube_search_no_os_defaults():
    # Canonical OS videos should NOT trigger for Big Data Analytics
    res1 = youtube_service.discover_topic_videos("Spark RDDs", subject_name="Big Data Analytics")
    assert res1 == []

    # And should not trigger when subject_name is None
    res2 = youtube_service.discover_topic_videos("Spark RDDs", subject_name=None)
    assert res2 == []

    # Canonical OS videos should ONLY trigger if subject is explicitly Operating Systems
    os_res = youtube_service.discover_topic_videos("Process Concepts", subject_name="Operating Systems")
    assert len(os_res) > 0
    assert os_res[0]["source"] == "auto"


def test_progress_recommendations_weak_vs_insufficient():
    db = MagicMock()
    student_id = str(uuid.uuid4())
    class_id = str(uuid.uuid4())
    subject_id = uuid.uuid4()

    mock_class = Class(id=uuid.UUID(class_id), name="Big Data Analytics A", subject_id=subject_id, subject="Big Data Analytics")
    mock_subject = Subject(id=subject_id, name="Big Data Analytics")

    topic_id_spark = uuid.uuid4()
    topic_id_hdfs = uuid.uuid4()
    topic_id_yarn = uuid.uuid4()

    mock_syllabus = [
        PrerequisiteMap(id=topic_id_spark, subject_id=subject_id, topic="Spark RDDs"),
        PrerequisiteMap(id=topic_id_hdfs, subject_id=subject_id, topic="HDFS Architecture"),
        PrerequisiteMap(id=topic_id_yarn, subject_id=subject_id, topic="YARN"),
    ]

    mastery_spark = TopicMastery(
        student_id=uuid.UUID(student_id),
        class_id=uuid.UUID(class_id),
        topic="Spark RDDs",
        mastery_score=0.35,
        attempt_count=3,
        trend=MasteryTrend.stable,
        mastery_v2=json.dumps({"mastery_band": "low", "evidence_state": "direct", "accuracy": 0.33}),
    )
    mastery_hdfs = TopicMastery(
        student_id=uuid.UUID(student_id),
        class_id=uuid.UUID(class_id),
        topic="HDFS Architecture",
        mastery_score=0.85,
        attempt_count=4,
        trend=MasteryTrend.improving,
        mastery_v2=json.dumps({"mastery_band": "high", "evidence_state": "direct", "accuracy": 0.90}),
    )
    # YARN has 0 attempts / insufficient
    mastery_yarn = TopicMastery(
        student_id=uuid.UUID(student_id),
        class_id=uuid.UUID(class_id),
        topic="YARN",
        mastery_score=0.0,
        attempt_count=0,
        trend=MasteryTrend.stable,
        mastery_v2=json.dumps({"mastery_band": "unassessed", "evidence_state": "insufficient", "accuracy": 0.0}),
    )

    def mock_get(entity, ident):
        if entity == Class:
            return mock_class
        if entity == Subject:
            return mock_subject
        return None

    def mock_query(*entities, **kwargs):
        query_mock = MagicMock()
        query_mock.join.return_value = query_mock
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.limit.return_value = query_mock
        if len(entities) == 1:
            entity = entities[0]
            if entity == TopicMastery:
                query_mock.all.return_value = [mastery_spark, mastery_hdfs, mastery_yarn]
            elif entity == PrerequisiteMap:
                query_mock.all.return_value = mock_syllabus
            elif entity == Quiz:
                query_mock.all.return_value = []
            else:
                query_mock.all.return_value = []
        else:
            query_mock.all.return_value = []
        return query_mock

    db.get.side_effect = mock_get
    db.query.side_effect = mock_query

    with patch("backend.services.recommendation_service._library_resources", return_value=([], [])), \
         patch("backend.services.youtube_service.discover_topic_videos", return_value=[]):
        res = recommendation_service.get_progress_recommendations(db, student_id=student_id, class_id=class_id)

    # 1. "Spark RDDs" should be in weak_topics
    weak_names = [g["topic"] for g in res["weak_topics"]]
    assert "Spark RDDs" in weak_names

    # 2. "HDFS Architecture" (85%) should NOT be in weak_topics
    assert "HDFS Architecture" not in weak_names

    # 3. "YARN" (0 attempts) should be in insufficient_evidence, NOT in weak_topics
    assert "YARN" not in weak_names
    insufficient_names = [i["topic"] for i in res["insufficient_evidence_topics"]]
    assert "YARN" in insufficient_names

    # 4. Each weak topic has at least practice quiz activity
    spark_group = next(g for g in res["weak_topics"] if g["topic"] == "Spark RDDs")
    assert len(spark_group["resources"]) > 0
    assert any(r["action"] == "practise" for r in spark_group["resources"])


def test_progress_recommendations_ranking():
    db = MagicMock()
    student_id = str(uuid.uuid4())
    class_id = str(uuid.uuid4())
    subject_id = uuid.uuid4()

    mock_class = Class(id=uuid.UUID(class_id), name="Big Data Analytics A", subject_id=subject_id, subject="Big Data Analytics")
    mock_subject = Subject(id=subject_id, name="Big Data Analytics")

    mock_syllabus = [
        PrerequisiteMap(id=uuid.uuid4(), subject_id=subject_id, topic="Spark RDDs"),
    ]

    mastery_spark = TopicMastery(
        student_id=uuid.UUID(student_id),
        class_id=uuid.UUID(class_id),
        topic="Spark RDDs",
        mastery_score=0.4,
        attempt_count=2,
        trend=MasteryTrend.stable,
        mastery_v2=json.dumps({"mastery_band": "low", "evidence_state": "direct", "accuracy": 0.4}),
    )

    # Faculty-curated YouTube video resource dictionary as returned by _library_resources
    curated_video = {
        "video_id": "12345678901",
        "title": "Faculty Curated Spark Masterclass",
        "channel": "Prof Spark",
        "duration": "25:00",
        "thumbnail": None,
        "source": "faculty",
        "embeddable": True,
        "url": "https://www.youtube.com/watch?v=12345678901",
        "helpful_count": 10,
    }

    auto_video = {
        "title": "Quick Spark Overview",
        "video_id": "abcdefghijk",
        "channel": "Tech channel",
        "url": "https://www.youtube.com/watch?v=abcdefghijk",
        "duration": "10:00",
        "thumbnail": None,
        "source": "auto",
        "embeddable": True,
    }

    def mock_get(entity, ident):
        if entity == Class:
            return mock_class
        if entity == Subject:
            return mock_subject
        return None

    def mock_query(*entities, **kwargs):
        query_mock = MagicMock()
        query_mock.join.return_value = query_mock
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.limit.return_value = query_mock
        if len(entities) == 1:
            entity = entities[0]
            if entity == TopicMastery:
                query_mock.all.return_value = [mastery_spark]
            elif entity == PrerequisiteMap:
                query_mock.all.return_value = mock_syllabus
            else:
                query_mock.all.return_value = []
        else:
            query_mock.all.return_value = []
        return query_mock

    db.get.side_effect = mock_get
    db.query.side_effect = mock_query

    with patch("backend.services.recommendation_service._library_resources", return_value=([curated_video], [])), \
         patch("backend.services.youtube_service.discover_topic_videos", return_value=[auto_video]):
        res = recommendation_service.get_progress_recommendations(db, student_id=student_id, class_id=class_id)

    spark_group = res["weak_topics"][0]
    recs = spark_group["resources"]

    # Top recommendation must be the Faculty Curated video
    assert recs[0]["source"] == "faculty"
    assert recs[0]["title"] == "Faculty Curated Spark Masterclass"
    assert recs[0]["action"] == "watch"
    assert recs[0]["action_label"] == "Watch Video"
