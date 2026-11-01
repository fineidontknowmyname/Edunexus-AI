import uuid
import pytest

from backend.models.db import (
    Category,
    Class,
    PrerequisiteMap,
    Subject,
    TopicMastery,
    MasteryTrend,
)
from backend.services import topic_graph_service


@pytest.fixture
def rename_setup(db, educator_user, student_user, sample_class):
    cat = db.query(Category).first()
    if not cat:
        cat = Category(name=f"Eng-{uuid.uuid4().hex[:4]}", created_by=educator_user.id)
        db.add(cat)
        db.commit()
        db.refresh(cat)

    subject = Subject(
        name=f"CS_{uuid.uuid4().hex[:6]}",
        category_id=cat.id,
        created_by=educator_user.id,
    )
    db.add(subject)
    db.commit()
    db.refresh(subject)

    sample_class.subject_id = subject.id
    sample_class.subject = subject.name
    db.commit()

    yield {
        "db": db,
        "subject": subject,
        "class": sample_class,
        "student": student_user,
    }

    # Cleanup
    db.query(TopicMastery).filter(TopicMastery.class_id == sample_class.id).delete()
    db.query(PrerequisiteMap).filter(PrerequisiteMap.subject_id == subject.id).delete()
    sample_class.subject_id = None
    db.commit()
    db.delete(subject)
    db.commit()


def test_rename_topic_simple_with_mastery(rename_setup):
    db = rename_setup["db"]
    subject = rename_setup["subject"]
    class_row = rename_setup["class"]
    student = rename_setup["student"]

    old_topic = f"Topic_Old_{uuid.uuid4().hex[:6]}"
    new_topic = f"Topic_New_{uuid.uuid4().hex[:6]}"

    prereq = PrerequisiteMap(
        id=uuid.uuid4(),
        subject_id=subject.id,
        subject=subject.name,
        topic=old_topic,
        created_by=str(student.id),
    )
    db.add(prereq)

    tm = TopicMastery(
        id=uuid.uuid4(),
        student_id=student.id,
        class_id=class_row.id,
        topic=old_topic,
        mastery_score=0.82,
        attempt_count=5,
        trend=MasteryTrend.improving,
    )
    db.add(tm)
    db.commit()

    # Call rename_topic
    topic_graph_service.rename_topic(db, str(subject.id), old_topic, new_topic)

    # Verify TopicMastery was updated properly
    updated_tm = (
        db.query(TopicMastery)
        .filter(TopicMastery.student_id == student.id, TopicMastery.class_id == class_row.id)
        .first()
    )
    assert updated_tm is not None
    assert updated_tm.topic == new_topic
    assert updated_tm.attempt_count == 5
    assert updated_tm.mastery_score == 0.82


def test_rename_topic_merge_with_existing_mastery(rename_setup):
    db = rename_setup["db"]
    subject = rename_setup["subject"]
    class_row = rename_setup["class"]
    student = rename_setup["student"]

    old_topic = f"Merge_Old_{uuid.uuid4().hex[:6]}"
    new_topic = f"Merge_New_{uuid.uuid4().hex[:6]}"

    p1 = PrerequisiteMap(
        id=uuid.uuid4(),
        subject_id=subject.id,
        subject=subject.name,
        topic=old_topic,
        created_by=str(student.id),
    )
    db.add(p1)

    tm_old = TopicMastery(
        id=uuid.uuid4(),
        student_id=student.id,
        class_id=class_row.id,
        topic=old_topic,
        mastery_score=0.60,
        attempt_count=3,
        trend=MasteryTrend.stable,
    )
    tm_target = TopicMastery(
        id=uuid.uuid4(),
        student_id=student.id,
        class_id=class_row.id,
        topic=new_topic,
        mastery_score=0.80,
        attempt_count=2,
        trend=MasteryTrend.improving,
    )
    db.add_all([tm_old, tm_target])
    db.commit()

    topic_graph_service.rename_topic(db, str(subject.id), old_topic, new_topic)

    # Should merge into a single row for new_topic
    masteries = (
        db.query(TopicMastery)
        .filter(TopicMastery.student_id == student.id, TopicMastery.class_id == class_row.id)
        .all()
    )
    assert len(masteries) == 1
    m = masteries[0]
    assert m.topic == new_topic
    assert m.attempt_count == 5  # 3 + 2


def test_rename_topic_atomicity_on_error(rename_setup, monkeypatch):
    db = rename_setup["db"]
    subject = rename_setup["subject"]
    student = rename_setup["student"]

    old_topic = f"Rollback_Old_{uuid.uuid4().hex[:6]}"
    new_topic = f"Rollback_New_{uuid.uuid4().hex[:6]}"

    p1 = PrerequisiteMap(
        id=uuid.uuid4(),
        subject_id=subject.id,
        subject=subject.name,
        topic=old_topic,
        created_by=str(student.id),
    )
    db.add(p1)
    db.commit()

    # Simulate an error inside the transaction, e.g. when _subject_class_ids is called
    def mock_fail(*args, **kwargs):
        raise RuntimeError("Simulated database failure during cascade")

    monkeypatch.setattr(topic_graph_service, "_subject_class_ids", mock_fail)

    with pytest.raises(RuntimeError, match="Simulated database failure"):
        topic_graph_service.rename_topic(db, str(subject.id), old_topic, new_topic)

    # PrerequisiteMap topic must NOT have been changed due to rollback
    p_check = db.query(PrerequisiteMap).filter(PrerequisiteMap.id == p1.id).first()
    assert p_check.topic == old_topic

