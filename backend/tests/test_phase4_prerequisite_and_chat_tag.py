import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import event

from backend.models.db import (
    Category,
    Class,
    MasteryTrend,
    PrerequisiteMap,
    RecommendationLog,
    Subject,
    TopicBehavior,
    TopicMastery,
    User,
    UserRole,
)
from backend.models.schemas import PrerequisiteAdvisory, RecommendationRead, RecommendationResponse
from backend.services import behavior_service, recommendation_service, routing_service


@pytest.fixture
def p4_context(db):
    """Fixture providing a managed test subject, class, and educator in the test DB."""
    created = []

    educator = User(
        id=uuid.uuid4(),
        email=f"p4_edu_{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="dummy_hash",
        full_name="P4 Educator",
        role=UserRole.educator,
        timezone="UTC",
    )
    student = User(
        id=uuid.uuid4(),
        email=f"p4_stu_{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="dummy_hash",
        full_name="P4 Student",
        role=UserRole.student,
        timezone="UTC",
    )
    db.add_all([educator, student])
    db.commit()
    created.extend([student, educator])

    cat = db.query(Category).first()
    if not cat:
        cat = Category(name=f"Cat-{uuid.uuid4().hex[:4]}", created_by=educator.id)
        db.add(cat)
        db.commit()
        db.refresh(cat)
        created.append(cat)

    subject = Subject(
        id=uuid.uuid4(),
        name=f"P4 Subject {uuid.uuid4().hex[:6]}",
        category_id=cat.id,
        created_by=educator.id,
    )
    db.add(subject)
    db.commit()
    db.refresh(subject)
    created.append(subject)

    class_row = Class(
        id=uuid.uuid4(),
        name=f"P4 Class {uuid.uuid4().hex[:6]}",
        subject_id=subject.id,
        subject=subject.name,
        join_code=uuid.uuid4().hex[:8],
        educator_id=educator.id,
    )
    db.add(class_row)
    db.commit()
    db.refresh(class_row)
    created.append(class_row)

    try:
        yield {
            "db": db,
            "subject": subject,
            "class": class_row,
            "educator": educator,
            "student": student,
            "created": created,
        }
    finally:
        # Clean up created records
        try:
            # Clean up any recommendation logs, topic masteries, and prerequisite maps first
            db.query(RecommendationLog).filter(RecommendationLog.class_id == class_row.id).delete(synchronize_session=False)
            db.query(TopicMastery).filter(TopicMastery.class_id == class_row.id).delete(synchronize_session=False)
            db.query(PrerequisiteMap).filter(PrerequisiteMap.subject_id == subject.id).delete(synchronize_session=False)
            for item in created:
                db.delete(item)
            db.commit()
        except Exception:
            db.rollback()


def test_prerequisite_unattempted_advisory_present(p4_context):
    """1. Prerequisite with no mastery row => advisory present, mode identical to the same student/topic without that prerequisite."""
    db = p4_context["db"]
    subject_id = p4_context["subject"].id
    class_id = p4_context["class"].id
    student_id = p4_context["student"].id

    # Topic B requires Topic A
    p_a = PrerequisiteMap(id=uuid.uuid4(), subject_id=subject_id, subject=p4_context["subject"].name, topic="Topic A", requires=[])
    p_b = PrerequisiteMap(id=uuid.uuid4(), subject_id=subject_id, subject=p4_context["subject"].name, topic="Topic B", requires=["Topic A"])
    db.add_all([p_a, p_b])

    # Student has mastery in Topic B (score 0.85, high band, sufficient) but NO row for Topic A
    m_b = TopicMastery(
        id=uuid.uuid4(),
        student_id=student_id,
        class_id=class_id,
        topic="Topic B",
        mastery_score=0.85,
        attempt_count=4,
        trend=MasteryTrend.stable,
        mastery_v2=json.dumps({"mastery_band": "high", "evidence_state": "sufficient", "accuracy": 0.85}),
    )
    db.add(m_b)
    db.commit()

    with patch("backend.services.recommendation_service._library_resources", return_value=([], [])), \
         patch("backend.services.recommendation_service._curriculum_sections", return_value=[]), \
         patch("backend.services.behavior_service.get_learning_tag", return_value=None), \
         patch("backend.services.routing_service.get_topic_routing", return_value="normal"):
        rec = recommendation_service.get_recommendation(db, str(student_id), str(class_id), str(subject_id), "Topic B", embedding_model=None)

    # Mode remains advance because student mastered Topic B
    assert rec["mode"] == "advance"
    # Advisory must be present for unattempted prerequisite Topic A
    assert rec.get("prerequisite_advisory") is not None
    adv = rec["prerequisite_advisory"]
    assert adv["topic"] == "Topic A"
    assert "Topic A" in adv["reason"]
    assert adv["attempted"] is False


def test_prerequisite_attempt_count_zero_triggers_advisory(p4_context):
    """2. Prerequisite row with attempt_count 0 => advisory present."""
    db = p4_context["db"]
    subject_id = p4_context["subject"].id
    class_id = p4_context["class"].id
    student_id = p4_context["student"].id

    p_a = PrerequisiteMap(id=uuid.uuid4(), subject_id=subject_id, subject=p4_context["subject"].name, topic="Kinematics", requires=[])
    p_b = PrerequisiteMap(id=uuid.uuid4(), subject_id=subject_id, subject=p4_context["subject"].name, topic="Dynamics", requires=["Kinematics"])
    db.add_all([p_a, p_b])

    # Kinematics has a row but attempt_count == 0
    m_a = TopicMastery(
        id=uuid.uuid4(),
        student_id=student_id,
        class_id=class_id,
        topic="Kinematics",
        mastery_score=0.0,
        attempt_count=0,
        trend=MasteryTrend.not_started,
    )
    m_b = TopicMastery(
        id=uuid.uuid4(),
        student_id=student_id,
        class_id=class_id,
        topic="Dynamics",
        mastery_score=0.65,
        attempt_count=3,
        trend=MasteryTrend.stable,
        mastery_v2=json.dumps({"mastery_band": "medium", "evidence_state": "sufficient", "accuracy": 0.65}),
    )
    db.add_all([m_a, m_b])
    db.commit()

    with patch("backend.services.recommendation_service._library_resources", return_value=([], [])), \
         patch("backend.services.recommendation_service._curriculum_sections", return_value=[]), \
         patch("backend.services.behavior_service.get_learning_tag", return_value=None), \
         patch("backend.services.routing_service.get_topic_routing", return_value="normal"):
        rec = recommendation_service.get_recommendation(db, str(student_id), str(class_id), str(subject_id), "Dynamics", embedding_model=None)

    assert rec["mode"] == "reinforce"
    assert rec.get("prerequisite_advisory") is not None
    assert rec["prerequisite_advisory"]["topic"] == "Kinematics"
    assert rec["prerequisite_advisory"]["attempted"] is False


def test_prerequisite_attempted_and_weak_triggers_ai_session_no_advisory(p4_context):
    """3. Prerequisite attempted and weak => existing behaviour unchanged (mode ai_session, no advisory)."""
    db = p4_context["db"]
    subject_id = p4_context["subject"].id
    class_id = p4_context["class"].id
    student_id = p4_context["student"].id

    p_a = PrerequisiteMap(id=uuid.uuid4(), subject_id=subject_id, subject=p4_context["subject"].name, topic="Pointers", requires=[])
    p_b = PrerequisiteMap(id=uuid.uuid4(), subject_id=subject_id, subject=p4_context["subject"].name, topic="Trees", requires=["Pointers"])
    db.add_all([p_a, p_b])

    # Pointers attempted and weak (attempt_count=2, score=0.45)
    m_a = TopicMastery(
        id=uuid.uuid4(),
        student_id=student_id,
        class_id=class_id,
        topic="Pointers",
        mastery_score=0.45,
        attempt_count=2,
        trend=MasteryTrend.stable,
    )
    db.add(m_a)
    db.commit()

    with patch("backend.services.recommendation_service._library_resources", return_value=([], [])), \
         patch("backend.services.recommendation_service._curriculum_sections", return_value=[]), \
         patch("backend.services.behavior_service.get_learning_tag", return_value=None), \
         patch("backend.services.routing_service.get_topic_routing", return_value="normal"):
        rec = recommendation_service.get_recommendation(db, str(student_id), str(class_id), str(subject_id), "Trees", embedding_model=None)

    # _check_prerequisite_gap triggers ai_session for weak prerequisite
    assert rec["mode"] == "ai_session"
    assert "pointers" in rec["reason"].lower()
    # No duplicate advisory attached
    assert rec.get("prerequisite_advisory") is None


def test_prerequisite_attempted_and_strong_no_advisory(p4_context):
    """4. Prerequisite attempted and strong => no advisory."""
    db = p4_context["db"]
    subject_id = p4_context["subject"].id
    class_id = p4_context["class"].id
    student_id = p4_context["student"].id

    p_a = PrerequisiteMap(id=uuid.uuid4(), subject_id=subject_id, subject=p4_context["subject"].name, topic="Variables", requires=[])
    p_b = PrerequisiteMap(id=uuid.uuid4(), subject_id=subject_id, subject=p4_context["subject"].name, topic="Loops", requires=["Variables"])
    db.add_all([p_a, p_b])

    m_a = TopicMastery(
        id=uuid.uuid4(),
        student_id=student_id,
        class_id=class_id,
        topic="Variables",
        mastery_score=0.90,
        attempt_count=4,
        trend=MasteryTrend.improving,
    )
    db.add(m_a)
    db.commit()

    with patch("backend.services.recommendation_service._library_resources", return_value=([], [])), \
         patch("backend.services.recommendation_service._curriculum_sections", return_value=[]), \
         patch("backend.services.behavior_service.get_learning_tag", return_value=None), \
         patch("backend.services.routing_service.get_topic_routing", return_value="normal"):
        rec = recommendation_service.get_recommendation(db, str(student_id), str(class_id), str(subject_id), "Loops", embedding_model=None)

    assert rec.get("prerequisite_advisory") is None


def test_find_unattempted_prerequisites_vocabulary_and_limit(p4_context):
    """5. Prerequisite not in syllabus vocabulary => no advisory; no prerequisites => no advisory; >2 unattempted => exactly 2 in order."""
    db = p4_context["db"]
    subject_id = p4_context["subject"].id
    class_id = p4_context["class"].id
    student_id = p4_context["student"].id

    # Topic with no prerequisites
    p_leaf = PrerequisiteMap(id=uuid.uuid4(), subject_id=subject_id, subject=p4_context["subject"].name, topic="Basic Math", requires=[])
    # Topic requiring stale name not in syllabus vocabulary
    p_stale = PrerequisiteMap(id=uuid.uuid4(), subject_id=subject_id, subject=p4_context["subject"].name, topic="Advanced Topic", requires=["Ghost Topic Not In Syllabus"])
    # Topic requiring 3 valid unattempted prerequisites
    p1 = PrerequisiteMap(id=uuid.uuid4(), subject_id=subject_id, subject=p4_context["subject"].name, topic="Pre 1", requires=[])
    p2 = PrerequisiteMap(id=uuid.uuid4(), subject_id=subject_id, subject=p4_context["subject"].name, topic="Pre 2", requires=[])
    p3 = PrerequisiteMap(id=uuid.uuid4(), subject_id=subject_id, subject=p4_context["subject"].name, topic="Pre 3", requires=[])
    p_multi = PrerequisiteMap(id=uuid.uuid4(), subject_id=subject_id, subject=p4_context["subject"].name, topic="Multi Pre Topic", requires=["Pre 1", "Pre 2", "Pre 3"])
    db.add_all([p_leaf, p_stale, p1, p2, p3, p_multi])
    db.commit()

    # Case A: No prerequisites -> empty list
    unatt_none = recommendation_service.find_unattempted_prerequisites(db, str(student_id), str(class_id), str(subject_id), "Basic Math")
    assert unatt_none == []

    # Case B: Stale prerequisite not in vocabulary -> empty list
    unatt_stale = recommendation_service.find_unattempted_prerequisites(db, str(student_id), str(class_id), str(subject_id), "Advanced Topic")
    assert unatt_stale == []

    # Case C: 3 unattempted prerequisites -> exactly 2 returned in order
    unatt_multi = recommendation_service.find_unattempted_prerequisites(db, str(student_id), str(class_id), str(subject_id), "Multi Pre Topic")
    assert unatt_multi == ["Pre 1", "Pre 2"]


def test_prerequisites_casing_and_whitespace_matching(p4_context):
    """6. Prerequisites matched with different casing/whitespace are treated as the same topic."""
    db = p4_context["db"]
    subject_id = p4_context["subject"].id
    class_id = p4_context["class"].id
    student_id = p4_context["student"].id

    # Prerequisite map has '  Operating Systems  ' in requires
    p_base = PrerequisiteMap(id=uuid.uuid4(), subject_id=subject_id, subject=p4_context["subject"].name, topic="Operating Systems", requires=[])
    p_target = PrerequisiteMap(id=uuid.uuid4(), subject_id=subject_id, subject=p4_context["subject"].name, topic="Virtual Memory", requires=["  operating systems  \n"])
    db.add_all([p_base, p_target])

    # TopicMastery stored with normal casing and attempted
    m_base = TopicMastery(
        id=uuid.uuid4(),
        student_id=student_id,
        class_id=class_id,
        topic="Operating Systems",
        mastery_score=0.8,
        attempt_count=3,
        trend=MasteryTrend.improving,
    )
    db.add(m_base)
    db.commit()

    unatt = recommendation_service.find_unattempted_prerequisites(db, str(student_id), str(class_id), str(subject_id), "virtual memory")
    assert unatt == []


def test_mastery_fetched_in_single_query(p4_context):
    """7. Mastery fetched in a single query for the prerequisite set (assert statement count)."""
    db = p4_context["db"]
    subject_id = p4_context["subject"].id
    class_id = p4_context["class"].id
    student_id = p4_context["student"].id

    p1 = PrerequisiteMap(id=uuid.uuid4(), subject_id=subject_id, subject=p4_context["subject"].name, topic="Req A", requires=[])
    p2 = PrerequisiteMap(id=uuid.uuid4(), subject_id=subject_id, subject=p4_context["subject"].name, topic="Req B", requires=[])
    p_target = PrerequisiteMap(id=uuid.uuid4(), subject_id=subject_id, subject=p4_context["subject"].name, topic="Complex Node", requires=["Req A", "Req B"])
    db.add_all([p1, p2, p_target])
    db.commit()

    mastery_queries = []

    def count_queries(conn, cursor, statement, parameters, context, executemany):
        if "topic_mastery" in statement.lower():
            mastery_queries.append(statement)

    event.listen(db.bind, "before_cursor_execute", count_queries)
    try:
        recommendation_service.find_unattempted_prerequisites(db, str(student_id), str(class_id), str(subject_id), "Complex Node")
    finally:
        event.remove(db.bind, "before_cursor_execute", count_queries)

    assert len(mastery_queries) == 1, f"Expected exactly 1 topic_mastery query, got {len(mastery_queries)}"


def test_chat_learning_tag_decision_matrix(p4_context):
    """8. Chat tag: medium+sufficient + 'needs-repetition' => ai_session; no tag => reinforce; high+sufficient => advance; insufficient => diagnostic; low+sufficient => ai_session; open misconception => intervene ai_session."""
    db = p4_context["db"]
    subject_id = p4_context["subject"].id
    class_id = p4_context["class"].id
    student_id = p4_context["student"].id

    topic = "Algorithms"
    p = PrerequisiteMap(id=uuid.uuid4(), subject_id=subject_id, subject=p4_context["subject"].name, topic=topic, requires=[])
    db.add(p)
    db.commit()

    def run_ladder(band, evidence, tag, routing="normal"):
        m = TopicMastery(
            id=uuid.uuid4(),
            student_id=student_id,
            class_id=class_id,
            topic=topic,
            mastery_score=0.65,
            attempt_count=3,
            trend=MasteryTrend.stable,
            mastery_v2=json.dumps({"mastery_band": band, "evidence_state": evidence, "accuracy": 0.65}),
        )
        db.query(TopicMastery).filter(TopicMastery.class_id == class_id, TopicMastery.topic == topic).delete()
        db.add(m)
        db.commit()

        with patch("backend.services.recommendation_service._library_resources", return_value=([], [])), \
             patch("backend.services.recommendation_service._curriculum_sections", return_value=[]), \
             patch("backend.services.behavior_service.get_learning_tag", return_value=tag), \
             patch("backend.services.routing_service.get_topic_routing", return_value=routing):
            return recommendation_service.get_recommendation(db, str(student_id), str(class_id), str(subject_id), topic, embedding_model=None)

    # 1. medium + sufficient + needs-repetition => ai_session (reason mentions questions/chat)
    r1 = run_ladder("medium", "sufficient", "needs-repetition")
    assert r1["mode"] == "ai_session"
    assert "follow-up questions" in r1["reason"].lower() or "chat" in r1["reason"].lower()

    # 2. medium + sufficient + None => reinforce
    r2 = run_ladder("medium", "sufficient", None)
    assert r2["mode"] == "reinforce"

    # 3. high + sufficient + needs-repetition => advance (must not be overridden)
    r3 = run_ladder("high", "sufficient", "needs-repetition")
    assert r3["mode"] == "advance"

    # 4. medium + insufficient + needs-repetition => diagnostic (must not be overridden)
    r4 = run_ladder("medium", "insufficient", "needs-repetition")
    assert r4["mode"] == "diagnostic"

    # 5. low + sufficient + needs-repetition => ai_session (unchanged)
    r5 = run_ladder("low", "sufficient", "needs-repetition")
    assert r5["mode"] == "ai_session"
    assert "persistent difficulty" in r5["reason"].lower()

    # 6. open misconception + needs-repetition => intervene ai_session (step 1 takes precedence)
    r6 = run_ladder("medium", "sufficient", "needs-repetition", routing="intervene")
    assert r6["mode"] == "ai_session"
    assert "open misconception" in r6["reason"].lower()


def test_response_schema_serialization():
    """9. Response schema: a response with no advisory serialises prerequisite_advisory as null and old clients/tests still pass."""
    # Case A: No advisory
    resp_no_adv = RecommendationRead(
        routing="normal",
        learning_tag=None,
        mode="advance",
        reason="Good job",
        sections=[],
        videos=[],
        notes=[],
    )
    dumped = resp_no_adv.model_dump()
    assert "prerequisite_advisory" in dumped
    assert dumped["prerequisite_advisory"] is None

    # Case B: With advisory
    resp_with_adv = RecommendationRead(
        routing="normal",
        learning_tag=None,
        mode="advance",
        reason="Good job",
        sections=[],
        videos=[],
        notes=[],
        prerequisite_advisory=PrerequisiteAdvisory(
            topic="Calculus I",
            reason="Before Calculus II, it helps to cover Calculus I. You haven't attempted it yet.",
            attempted=False,
        ),
    )
    dumped_adv = resp_with_adv.model_dump()
    assert dumped_adv["prerequisite_advisory"]["topic"] == "Calculus I"
    assert dumped_adv["prerequisite_advisory"]["attempted"] is False
    assert "Calculus I" in dumped_adv["prerequisite_advisory"]["reason"]
