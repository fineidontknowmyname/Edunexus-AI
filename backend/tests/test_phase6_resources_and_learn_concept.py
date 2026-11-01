import json
import uuid
import pytest
from fastapi.testclient import TestClient

from backend.models.db import (
    Category,
    Chunk,
    Class,
    ClassEnrollment,
    Document,
    DocumentFile,
    DocumentStatus,
    LearningResource,
    PrerequisiteMap,
    ResourceType,
    ReviewStatus,
    Subject,
    TopicMastery,
    User,
    UserRole,
)
from backend.models.schemas import ProgressRecommendationItem
from backend.services import recommendation_service, youtube_service
from backend.tests.conftest import auth_headers


@pytest.fixture
def test_setup(db, educator_user, student_user, sample_class):
    """Sets up a complete class, subject, syllabus topic, and enrolled student."""
    cat = db.query(Category).first()
    if not cat:
        cat = Category(name=f"Science-{uuid.uuid4().hex[:4]}", created_by=educator_user.id)
        db.add(cat)
        db.commit()
        db.refresh(cat)

    # Create Subject
    subject = Subject(
        name=f"Cell Bio - {uuid.uuid4().hex[:6]}",
        category_id=cat.id,
        created_by=educator_user.id,
    )
    db.add(subject)
    db.commit()
    db.refresh(subject)

    # Link subject to class
    sample_class.subject_id = subject.id
    sample_class.subject = subject.name
    db.commit()

    # Enroll student in class
    enrollment = ClassEnrollment(
        class_id=sample_class.id,
        student_id=student_user.id,
    )
    db.add(enrollment)
    db.commit()

    # Create canonical topic in PrerequisiteMap
    topic_row = PrerequisiteMap(
        subject_id=subject.id,
        topic="Cellular Respiration",
        order_index=1,
        is_canonical=True,
        created_by=educator_user.id,
    )
    db.add(topic_row)
    db.commit()
    db.refresh(topic_row)

    yield {
        "educator": educator_user,
        "student": student_user,
        "class": sample_class,
        "subject": subject,
        "topic": topic_row,
    }

    # Cleanup in strict foreign key order
    db.rollback()
    db.query(LearningResource).filter(LearningResource.class_id == sample_class.id).delete()
    db.query(TopicMastery).filter(TopicMastery.class_id == sample_class.id).delete()
    db.query(Chunk).filter(Chunk.class_id == sample_class.id).delete()
    docs = db.query(Document).filter(Document.class_id == sample_class.id).all()
    for d in docs:
        db.query(DocumentFile).filter(DocumentFile.document_id == d.id).delete()
    db.query(Document).filter(Document.class_id == sample_class.id).delete()
    db.query(PrerequisiteMap).filter(PrerequisiteMap.subject_id == subject.id).delete()
    db.query(ClassEnrollment).filter(ClassEnrollment.class_id == sample_class.id).delete()
    sample_class.subject_id = None
    sample_class.subject = None
    db.commit()
    db.delete(subject)
    db.commit()


def test_faculty_youtube_resource_creation_and_persistence(client, test_setup, db):
    """Test 1: Educator creates YouTube resource with metadata persistence and auto-approval."""
    edu = test_setup["educator"]
    cls = test_setup["class"]
    topic = test_setup["topic"]

    payload = {
        "class_id": str(cls.id),
        "topic": topic.topic,
        "topic_id": str(topic.id),
        "title": "Cellular Respiration In-Depth",
        "resource_type": "youtube",
        "url": "https://www.youtube.com/watch?v=00jbG_cfGuQ",
    }

    resp = client.post("/api/v1/resources", json=payload, headers=auth_headers(edu))
    assert resp.status_code == 201
    data = resp.json()

    assert data["topic"] == "Cellular Respiration"
    assert data["status"] == "approved"
    assert data["video_id"] == "00jbG_cfGuQ"
    assert data["source"] == "faculty"

    # Verify database persistence
    db_row = db.query(LearningResource).filter(LearningResource.id == uuid.UUID(data["id"])).first()
    assert db_row is not None
    assert db_row.status == ReviewStatus.approved
    assert db_row.resource_type == ResourceType.youtube

    # Verify JSON content metadata
    content_meta = json.loads(db_row.content)
    assert content_meta["video_id"] == "00jbG_cfGuQ"
    assert content_meta["source"] == "faculty"
    assert content_meta["topic_id"] == str(topic.id)


def test_youtube_url_normalization_and_validation(client, test_setup):
    """Test 2: Normalizes various YouTube URL formats and rejects invalid URLs."""
    edu = test_setup["educator"]
    cls = test_setup["class"]
    topic = test_setup["topic"]

    # Valid youtu.be format
    payload = {
        "class_id": str(cls.id),
        "topic": topic.topic,
        "topic_id": str(topic.id),
        "title": "Shorts Link",
        "resource_type": "youtube",
        "url": "https://youtu.be/00jbG_cfGuQ",
    }
    resp = client.post("/api/v1/resources", json=payload, headers=auth_headers(edu))
    assert resp.status_code == 201
    assert resp.json()["video_id"] == "00jbG_cfGuQ"
    assert resp.json()["url"] == "https://www.youtube.com/watch?v=00jbG_cfGuQ"

    # Invalid URL format (e.g. Vimeo)
    payload_invalid = {
        "class_id": str(cls.id),
        "topic": topic.topic,
        "topic_id": str(topic.id),
        "title": "Invalid Video",
        "resource_type": "youtube",
        "url": "https://vimeo.com/12345678",
    }
    resp_inv = client.post("/api/v1/resources", json=payload_invalid, headers=auth_headers(edu))
    assert resp_inv.status_code == 400
    assert "Invalid YouTube URL" in resp_inv.json()["detail"]


def test_duplicate_resource_prevention(client, test_setup, db):
    """Test 3: Avoids duplicate records when same URL is submitted repeatedly."""
    edu = test_setup["educator"]
    cls = test_setup["class"]
    topic = test_setup["topic"]

    payload = {
        "class_id": str(cls.id),
        "topic": topic.topic,
        "topic_id": str(topic.id),
        "title": "Cellular Respiration Overview",
        "resource_type": "youtube",
        "url": "https://www.youtube.com/watch?v=00jbG_cfGuQ",
    }

    # First submission
    resp1 = client.post("/api/v1/resources", json=payload, headers=auth_headers(edu))
    assert resp1.status_code == 201
    res1_id = resp1.json()["id"]

    # Second submission (identical)
    resp2 = client.post("/api/v1/resources", json=payload, headers=auth_headers(edu))
    assert resp2.status_code == 201
    res2_id = resp2.json()["id"]

    # Must return the existing resource instead of creating a duplicate row
    assert res1_id == res2_id
    count = db.query(LearningResource).filter(
        LearningResource.class_id == cls.id,
        LearningResource.url == "https://www.youtube.com/watch?v=00jbG_cfGuQ",
    ).count()
    assert count == 1


def test_recommendation_contract_includes_video_id(client, test_setup, db):
    """Test 4: Progress recommendation schema includes video_id for frontend VideoPlayerModal."""
    stu = test_setup["student"]
    cls = test_setup["class"]
    topic = test_setup["topic"]

    # Create approved faculty video resource
    res = LearningResource(
        class_id=cls.id,
        topic=topic.topic,
        title="ATP Synthesis Lecture",
        resource_type=ResourceType.youtube,
        url="https://www.youtube.com/watch?v=00jbG_cfGuQ",
        content=json.dumps({"video_id": "00jbG_cfGuQ", "source": "faculty", "channel": "Bio Professor"}),
        status=ReviewStatus.approved,
        uploaded_by_id=test_setup["educator"].id,
    )
    db.add(res)

    # Set student mastery on topic to weak (<0.60)
    mastery = TopicMastery(
        student_id=stu.id,
        class_id=cls.id,
        topic=topic.topic,
        mastery_score=0.45,
        attempt_count=3,
        mastery_v2=json.dumps({"mastery_band": "low", "evidence_state": "sufficient"}),
    )
    db.add(mastery)
    db.commit()

    resp = client.get(f"/api/v1/progress/recommendations?class_id={cls.id}", headers=auth_headers(stu))
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["weak_topics"]) > 0
    weak_group = next((g for g in data["weak_topics"] if g["topic"] == topic.topic), None)
    assert weak_group is not None

    video_items = [r for r in weak_group["resources"] if r["resource_type"] == "youtube"]
    assert len(video_items) >= 1
    v_item = video_items[0]

    # Verify video_id contract
    assert "video_id" in v_item
    assert v_item["video_id"] == "00jbG_cfGuQ"
    assert v_item["action"] == "watch"
    assert v_item["source"] == "faculty"


def test_case_insensitive_and_whitespace_topic_matching(client, test_setup, db):
    """Test 5: Topic matching is case-insensitive and trims whitespace."""
    stu = test_setup["student"]
    cls = test_setup["class"]

    # Add resource with leading/trailing spaces and different casing
    res = LearningResource(
        class_id=cls.id,
        topic="  cellular respiration  ",
        title="Cellular Respiration Crash Course",
        resource_type=ResourceType.youtube,
        url="https://www.youtube.com/watch?v=00jbG_cfGuQ",
        content=json.dumps({"video_id": "00jbG_cfGuQ", "source": "faculty"}),
        status=ReviewStatus.approved,
        uploaded_by_id=test_setup["educator"].id,
    )
    db.add(res)

    # Student weak topic has title case
    mastery = TopicMastery(
        student_id=stu.id,
        class_id=cls.id,
        topic="Cellular Respiration",
        mastery_score=0.40,
        attempt_count=2,
        mastery_v2=json.dumps({"mastery_band": "low", "evidence_state": "sufficient"}),
    )
    db.add(mastery)
    db.commit()

    resp = client.get(f"/api/v1/progress/recommendations?class_id={cls.id}", headers=auth_headers(stu))
    assert resp.status_code == 200
    data = resp.json()

    group = next((g for g in data["weak_topics"] if g["topic"] == "Cellular Respiration"), None)
    assert group is not None
    # Must retrieve the resource despite casing/whitespace difference
    matching_vids = [r for r in group["resources"] if r.get("video_id") == "00jbG_cfGuQ"]
    assert len(matching_vids) == 1


def test_class_and_subject_isolation(client, test_setup, db, educator_user):
    """Test 7: Resources and documents from other classes are strictly isolated."""
    stu = test_setup["student"]
    cls_a = test_setup["class"]

    # Create another separate class
    cls_b = Class(
        name=f"Different Class - {uuid.uuid4().hex[:6]}",
        subject="Chemistry",
        semester=1,
        educator_id=educator_user.id,
        join_code=uuid.uuid4().hex[:8].upper(),
    )
    db.add(cls_b)
    db.commit()

    # Resource in Class B
    res_b = LearningResource(
        class_id=cls_b.id,
        topic="Cellular Respiration",
        title="Class B Exclusive Resource",
        resource_type=ResourceType.youtube,
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        content=json.dumps({"video_id": "dQw4w9WgXcQ", "source": "faculty"}),
        status=ReviewStatus.approved,
        uploaded_by_id=educator_user.id,
    )
    db.add(res_b)

    # Student weak topic in Class A
    mastery = TopicMastery(
        student_id=stu.id,
        class_id=cls_a.id,
        topic="Cellular Respiration",
        mastery_score=0.35,
        attempt_count=2,
        mastery_v2=json.dumps({"mastery_band": "low", "evidence_state": "sufficient"}),
    )
    db.add(mastery)
    db.commit()

    resp = client.get(f"/api/v1/progress/recommendations?class_id={cls_a.id}", headers=auth_headers(stu))
    data = resp.json()

    group = next((g for g in data["weak_topics"] if g["topic"] == "Cellular Respiration"), None)
    assert group is not None
    # Must NOT include Class B's resource
    class_b_items = [r for r in group["resources"] if r.get("video_id") == "dQw4w9WgXcQ"]
    assert len(class_b_items) == 0

    # Cleanup Class B
    db.query(LearningResource).filter(LearningResource.class_id == cls_b.id).delete()
    db.delete(cls_b)
    db.commit()


def test_reliable_document_topic_retrieval(client, test_setup, db):
    """Test 9 & 13: Faculty uploaded course document is retrieved for weak topic and accessible to enrolled student."""
    stu = test_setup["student"]
    edu = test_setup["educator"]
    cls = test_setup["class"]
    topic = test_setup["topic"]

    # Create Document and binary DocumentFile in this class
    doc = Document(
        title="Cell Bio Lecture 4 - Respiration Notes",
        filename="lecture4_respiration.pdf",
        mime_type="application/pdf",
        class_id=cls.id,
        uploaded_by_id=edu.id,
        file_hash_sha256="abc123sha256",
        file_size_bytes=1024,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    doc_file = DocumentFile(
        document_id=doc.id,
        data=b"%PDF-1.4 test respiration notes data",
        size_bytes=34,
    )
    db.add(doc_file)

    # Tag PrerequisiteMap canonical topic with this source document
    topic.source_document_id = doc.id
    topic.source_page_number = 12

    # Student weak topic
    mastery = TopicMastery(
        student_id=stu.id,
        class_id=cls.id,
        topic="Cellular Respiration",
        mastery_score=0.45,
        attempt_count=2,
        mastery_v2=json.dumps({"mastery_band": "low", "evidence_state": "sufficient"}),
    )
    db.add(mastery)
    db.commit()

    # Progress recommendations should now contain the course document
    resp = client.get(f"/api/v1/progress/recommendations?class_id={cls.id}", headers=auth_headers(stu))
    assert resp.status_code == 200
    data = resp.json()

    group = next((g for g in data["weak_topics"] if g["topic"] == "Cellular Respiration"), None)
    assert group is not None

    doc_items = [r for r in group["resources"] if r.get("document_id") == str(doc.id)]
    assert len(doc_items) >= 1
    doc_item = doc_items[0]

    assert doc_item["action"] == "read"
    assert doc_item["action_label"] == "Read Document"
    assert doc_item["document_id"] == str(doc.id)
    assert doc_item["file_url"] == f"/api/v1/documents/{doc.id}/file"
    assert doc_item["source"] == "faculty"

    # Enrolled student can download/view original document
    file_resp = client.get(f"/api/v1/documents/{doc.id}/file", headers=auth_headers(stu))
    assert file_resp.status_code == 200
    assert file_resp.content == b"%PDF-1.4 test respiration notes data"
    assert "inline" in file_resp.headers["Content-Disposition"]
    assert "lecture4_respiration.pdf" in file_resp.headers["Content-Disposition"]


def test_unauthorized_student_document_access_rejected(client, test_setup, db):
    """Test 14: Non-enrolled student is rejected from viewing class documents."""
    edu = test_setup["educator"]
    cls = test_setup["class"]

    # Create document in class
    doc = Document(
        title="Class Notes",
        filename="notes.pdf",
        mime_type="application/pdf",
        class_id=cls.id,
        uploaded_by_id=edu.id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    db.add(DocumentFile(document_id=doc.id, data=b"secret notes", size_bytes=12))
    db.commit()

    # Create outsider student not enrolled in class
    outsider = User(
        email=f"outsider_{uuid.uuid4().hex[:6]}@test.io",
        hashed_password="pw",
        full_name="Outsider Student",
        role=UserRole.student,
    )
    db.add(outsider)
    db.commit()

    # Outsider requests document file
    resp = client.get(f"/api/v1/documents/{doc.id}/file", headers=auth_headers(outsider))
    assert resp.status_code == 404  # Not found due to class authorization check

    # Cleanup outsider
    db.delete(outsider)
    db.commit()


def test_exclusion_of_unrelated_documents(client, test_setup, db):
    """Test 10: Documents for other topics do not leak into this topic's recommendations."""
    stu = test_setup["student"]
    edu = test_setup["educator"]
    cls = test_setup["class"]
    subject = test_setup["subject"]

    # Create document for an unrelated topic (e.g. Genetics)
    unrelated_doc = Document(
        title="Mendelian Genetics Lab Manual",
        filename="genetics_lab.pdf",
        mime_type="application/pdf",
        class_id=cls.id,
        uploaded_by_id=edu.id,
    )
    db.add(unrelated_doc)
    db.commit()
    db.refresh(unrelated_doc)
    db.add(DocumentFile(document_id=unrelated_doc.id, data=b"genetics content", size_bytes=16))

    # Canonical topic for Genetics pointing to unrelated_doc
    genetics_topic = PrerequisiteMap(
        subject_id=subject.id,
        topic="Mendelian Genetics",
        source_document_id=unrelated_doc.id,
        created_by=edu.id,
    )
    db.add(genetics_topic)

    # Student weak topic is Cellular Respiration
    mastery = TopicMastery(
        student_id=stu.id,
        class_id=cls.id,
        topic="Cellular Respiration",
        mastery_score=0.45,
        attempt_count=2,
        mastery_v2=json.dumps({"mastery_band": "low", "evidence_state": "sufficient"}),
    )
    db.add(mastery)
    db.commit()

    resp = client.get(f"/api/v1/progress/recommendations?class_id={cls.id}", headers=auth_headers(stu))
    data = resp.json()

    group = next((g for g in data["weak_topics"] if g["topic"] == "Cellular Respiration"), None)
    assert group is not None

    # Genetics document must NOT appear in Cellular Respiration resources
    genetics_items = [r for r in group["resources"] if r.get("document_id") == str(unrelated_doc.id)]
    assert len(genetics_items) == 0
    assert group is not None

    # Genetics document must NOT appear in Cellular Respiration resources
    genetics_items = [r for r in group["resources"] if r.get("document_id") == str(unrelated_doc.id)]
    assert len(genetics_items) == 0


def test_malformed_legacy_resource_metadata_gracefully_handled(db):
    """Test 12: Handles corrupted content JSON and extracts valid video ID from URL."""
    cls_id = str(uuid.uuid4())
    res = LearningResource(
        class_id=uuid.UUID(cls_id),
        topic="Photosynthesis",
        title="Light Reactions",
        resource_type=ResourceType.youtube,
        url="https://www.youtube.com/watch?v=sQK3Yr4Sc_k",
        content="corrupted {json invalid",
        status=ReviewStatus.approved,
        uploaded_by_id=uuid.uuid4(),
    )

    class MockUser:
        role = UserRole.educator

    class MockQuery:
        def join(self, *a, **kw):
            return self
        def filter(self, *a, **kw):
            return self
        def order_by(self, *a, **kw):
            return self
        def all(self):
            return [(res, UserRole.educator)]

    class MockDb:
        def query(self, *a, **kw):
            return MockQuery()

    videos, notes = recommendation_service._library_resources(
        db=MockDb(),
        class_id=cls_id,
        topic="Photosynthesis",
    )

    assert len(videos) == 1
    # Fallback to URL extraction works cleanly without throwing JSONDecodeError
    assert videos[0]["video_id"] == "sQK3Yr4Sc_k"
    assert videos[0]["source"] == "faculty"
