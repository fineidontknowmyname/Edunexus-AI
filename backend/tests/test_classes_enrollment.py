import uuid
import pytest
from sqlalchemy.exc import IntegrityError
from backend.models.db import Class, ClassEnrollment, Misconception, TopicMastery
from backend.tests.conftest import auth_headers


def test_enroll_bad_uuid_returns_404(client, student_user):
    """Passing a non-UUID string in the URL must return 404, not a 500 error."""
    resp = client.post(
        "/api/v1/classes/not-a-valid-uuid/enroll",
        json={"join_code": "ANYCODE1"},
        headers=auth_headers(student_user),
    )
    assert resp.status_code == 404
    assert "not found" in resp.json().get("detail", "").lower()


def test_enroll_wrong_join_code_returns_403(client, student_user, sample_class):
    """Attempting to enroll with an incorrect join code must return 403 Forbidden."""
    resp = client.post(
        f"/api/v1/classes/{sample_class.id}/enroll",
        json={"join_code": "WRONG123"},
        headers=auth_headers(student_user),
    )
    assert resp.status_code == 403
    assert "incorrect join code" in resp.json().get("detail", "").lower()


def test_enroll_correct_join_code_succeeds(client, student_user, sample_class, db):
    """Enrolling with the correct join code creates an enrollment row and returns 201."""
    resp = client.post(
        f"/api/v1/classes/{sample_class.id}/enroll",
        json={"join_code": sample_class.join_code},
        headers=auth_headers(student_user),
    )
    assert resp.status_code == 201
    assert "enrolled in" in resp.json().get("message", "").lower()

    # Verify DB record
    enrollment = (
        db.query(ClassEnrollment)
        .filter(
            ClassEnrollment.class_id == sample_class.id,
            ClassEnrollment.student_id == student_user.id,
        )
        .first()
    )
    assert enrollment is not None


def test_enroll_twice_sequential_is_idempotent(client, student_user, sample_class, db):
    """Re-enrolling in an already-enrolled class does not fail or duplicate rows."""
    headers = auth_headers(student_user)
    payload = {"join_code": sample_class.join_code}

    # First enrollment
    r1 = client.post(f"/api/v1/classes/{sample_class.id}/enroll", json=payload, headers=headers)
    assert r1.status_code == 201

    # Second enrollment (same student, same class)
    r2 = client.post(f"/api/v1/classes/{sample_class.id}/enroll", json=payload, headers=headers)
    assert r2.status_code in (200, 201)

    # Verify exactly one enrollment exists
    count = (
        db.query(ClassEnrollment)
        .filter(
            ClassEnrollment.class_id == sample_class.id,
            ClassEnrollment.student_id == student_user.id,
        )
        .count()
    )
    assert count == 1


def test_db_unique_constraint_prevents_duplicate_enrollment(db, student_user, sample_class):
    """DB unique constraint on (class_id, student_id) raises IntegrityError on duplicates."""
    e1 = ClassEnrollment(class_id=sample_class.id, student_id=student_user.id)
    db.add(e1)
    db.commit()

    e2 = ClassEnrollment(class_id=sample_class.id, student_id=student_user.id)
    db.add(e2)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_leave_own_class_preserves_progress(client, student_user, sample_class, db):
    """Leaving a class deletes the enrollment row but keeps progress data (topic mastery)."""
    headers = auth_headers(student_user)

    # 1. Enroll
    client.post(
        f"/api/v1/classes/{sample_class.id}/enroll",
        json={"join_code": sample_class.join_code},
        headers=headers,
    )

    # 2. Add progress data (TopicMastery)
    mastery = TopicMastery(
        student_id=student_user.id,
        class_id=sample_class.id,
        topic="Mechanics",
        mastery_score=0.85,
        attempt_count=3,
    )
    db.add(mastery)
    db.commit()

    # 3. Leave the class
    leave_resp = client.delete(
        f"/api/v1/classes/{sample_class.id}/enroll",
        headers=headers,
    )
    assert leave_resp.status_code == 204

    # 4. Verify enrollment row is gone
    enrollment = (
        db.query(ClassEnrollment)
        .filter(
            ClassEnrollment.class_id == sample_class.id,
            ClassEnrollment.student_id == student_user.id,
        )
        .first()
    )
    assert enrollment is None

    # 5. Verify progress data is still intact
    retained_mastery = (
        db.query(TopicMastery)
        .filter(
            TopicMastery.student_id == student_user.id,
            TopicMastery.class_id == sample_class.id,
        )
        .first()
    )
    assert retained_mastery is not None
    assert retained_mastery.mastery_score == 0.85


def test_leave_unenrolled_class_returns_404(client, student_user, sample_class):
    """Attempting to leave a class that the student is not in returns 404."""
    resp = client.delete(
        f"/api/v1/classes/{sample_class.id}/enroll",
        headers=auth_headers(student_user),
    )
    assert resp.status_code == 404
    assert "not enrolled" in resp.json().get("detail", "").lower()


def test_leave_as_educator_returns_403(client, educator_user, sample_class):
    """Educators cannot call the student leave endpoint."""
    resp = client.delete(
        f"/api/v1/classes/{sample_class.id}/enroll",
        headers=auth_headers(educator_user),
    )
    assert resp.status_code == 403


def test_browse_classes_excludes_already_enrolled(client, student_user, sample_class, educator_user, db):
    """Browse endpoint returns available classes but excludes ones the student is enrolled in."""
    headers = auth_headers(student_user)

    # Create a second class
    class_b = Class(
        name=f"Chemistry 201 - {uuid.uuid4().hex[:6]}",
        subject="Chemistry",
        semester=2,
        educator_id=educator_user.id,
        join_code=uuid.uuid4().hex[:8].upper(),
    )
    db.add(class_b)
    db.commit()

    try:
        # Enroll in sample_class
        client.post(
            f"/api/v1/classes/{sample_class.id}/enroll",
            json={"join_code": sample_class.join_code},
            headers=headers,
        )

        # Browse classes
        resp = client.get("/api/v1/classes/browse", headers=headers)
        assert resp.status_code == 200
        browse_items = resp.json()
        browse_ids = [item["id"] for item in browse_items]

        # sample_class should NOT be in browse list (already enrolled)
        assert str(sample_class.id) not in browse_ids
        # class_b SHOULD be in browse list
        assert str(class_b.id) in browse_ids

        # Verify fields returned omit educator_id and join_code
        for item in browse_items:
            assert "educator_id" not in item, "educator_id must be omitted from browse"
            assert "join_code" not in item, "join_code must be omitted from browse"
    finally:
        db.delete(class_b)
        db.commit()


def test_insights_excludes_left_students(client, educator_user, student_user, sample_class, db):
    """Heatmap and common misconceptions in class insights must exclude students who left the class."""
    student_headers = auth_headers(student_user)
    educator_headers = auth_headers(educator_user)

    # 1. Student enrolls
    client.post(
        f"/api/v1/classes/{sample_class.id}/enroll",
        json={"join_code": sample_class.join_code},
        headers=student_headers,
    )

    # 2. Add topic mastery and misconception for this student
    topic_name = f"Quantum-{uuid.uuid4().hex[:4]}"
    mastery = TopicMastery(
        student_id=student_user.id,
        class_id=sample_class.id,
        topic=topic_name,
        mastery_score=0.25,  # struggling
        attempt_count=2,
    )
    misconception = Misconception(
        student_id=student_user.id,
        class_id=sample_class.id,
        topic=topic_name,
        description="Confuses wave and particle",
        resolved=False,
    )
    db.add(mastery)
    db.add(misconception)
    db.commit()

    # 3. Check insights while enrolled
    r_before = client.get(f"/api/v1/insights/class/{sample_class.id}", headers=educator_headers)
    assert r_before.status_code == 200
    heatmap_before = r_before.json()["heatmap"]
    topics_before = [h["topic"] for h in heatmap_before]
    assert topic_name in topics_before

    misconceptions_before = r_before.json()["misconceptions"]
    assert any(m["topic"] == topic_name for m in misconceptions_before)

    # 4. Student leaves class
    leave_resp = client.delete(f"/api/v1/classes/{sample_class.id}/enroll", headers=student_headers)
    assert leave_resp.status_code == 204

    # 5. Check insights after student left: student must no longer appear in heatmap or misconceptions
    r_after = client.get(f"/api/v1/insights/class/{sample_class.id}", headers=educator_headers)
    assert r_after.status_code == 200
    heatmap_after = r_after.json()["heatmap"]
    topics_after = [h["topic"] for h in heatmap_after]
    assert topic_name not in topics_after, "Left student must be excluded from heatmap"

    misconceptions_after = r_after.json()["misconceptions"]
    assert not any(m["topic"] == topic_name for m in misconceptions_after), (
        "Left student must be excluded from common misconceptions"
    )
