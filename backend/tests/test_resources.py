from datetime import datetime, timezone
import uuid
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException

from backend.api.resources import (
    _validate_youtube_url,
    create_resource,
    get_resource,
    list_resources,
    report_resource,
    review_resource,
    vote_resource,
)
from backend.models import schemas
from backend.models.db import Class, LearningResource, ResourceType, ResourceVote, ReviewStatus, User, UserRole


def test_validate_youtube_url():
    # Valid formats
    assert _validate_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert _validate_youtube_url("https://m.youtube.com/watch?v=dQw4w9WgXcQ") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert _validate_youtube_url("http://m.youtube.com/watch?v=dQw4w9WgXcQ&feature=shared") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert _validate_youtube_url("https://youtu.be/dQw4w9WgXcQ") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert _validate_youtube_url("http://youtube.com/watch?v=dQw4w9WgXcQ&t=10s") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert _validate_youtube_url("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    # Invalid formats
    with pytest.raises(HTTPException) as exc1:
        _validate_youtube_url("https://vimeo.com/12345678")
    assert exc1.value.status_code == 400

    with pytest.raises(HTTPException) as exc2:
        _validate_youtube_url("not a url")
    assert exc2.value.status_code == 400


def test_create_resource_youtube_by_student():
    mock_db = MagicMock()
    class_id = uuid.uuid4()
    student_id = uuid.uuid4()

    mock_user = User(id=student_id, full_name="Alice Student", role=UserRole.student)
    mock_class = Class(id=class_id, name="OS 101")

    payload = schemas.LearningResourceCreate(
        class_id=str(class_id),
        topic="Deadlocks",
        title="Great video on Banker's Algorithm",
        resource_type="youtube",
        url="https://youtu.be/dQw4w9WgXcQ",
    )

    with patch("backend.api.access.user_class_access", return_value=mock_class):
        res = create_resource(payload=payload, db=mock_db, current_user=mock_user)

    assert res.topic == "Deadlocks"
    assert res.resource_type == "youtube"
    assert res.status == "pending_review"  # Student upload requires review
    assert res.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()


def test_create_resource_notes_by_educator():
    mock_db = MagicMock()
    class_id = uuid.uuid4()
    educator_id = uuid.uuid4()

    mock_user = User(id=educator_id, full_name="Prof Bob", role=UserRole.educator)
    mock_class = Class(id=class_id, name="OS 101")

    payload = schemas.LearningResourceCreate(
        class_id=str(class_id),
        topic="Virtual Memory",
        title="Page Replacement Summary Notes",
        resource_type="notes",
        content="Here are the key takeaways for LRU vs FIFO...",
    )

    with patch("backend.api.access.user_class_access", return_value=mock_class):
        res = create_resource(payload=payload, db=mock_db, current_user=mock_user)

    assert res.topic == "Virtual Memory"
    assert res.resource_type == "notes"
    assert res.status == "approved"  # Educator upload is auto-approved
    assert res.content.startswith("Here are the key takeaways")
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()


def test_create_resource_empty_content_fails():
    mock_db = MagicMock()
    mock_user = User(id=uuid.uuid4(), full_name="Alice", role=UserRole.student)
    mock_class = Class(id=uuid.uuid4(), name="OS 101")

    payload = schemas.LearningResourceCreate(
        class_id=str(mock_class.id),
        topic="Deadlocks",
        title="Notes",
        resource_type="notes",
        content="   ",
    )

    with patch("backend.api.access.user_class_access", return_value=mock_class):
        with pytest.raises(HTTPException) as exc:
            create_resource(payload=payload, db=mock_db, current_user=mock_user)
        assert exc.value.status_code == 400


def test_vote_resource_idempotency():
    mock_db = MagicMock()
    res_id = uuid.uuid4()
    student_id = uuid.uuid4()
    uploader_id = uuid.uuid4()

    mock_user = User(id=student_id, full_name="Alice", role=UserRole.student)
    mock_uploader = User(id=uploader_id, full_name="Bob", role=UserRole.student)
    mock_res = LearningResource(
        id=res_id,
        class_id=uuid.uuid4(),
        topic="CPU Scheduling",
        title="Scheduling Guide",
        resource_type=ResourceType.notes,
        status=ReviewStatus.approved,
        helpful_count=5,
        report_count=0,
        uploaded_by_id=uploader_id,
    )

    # First vote: no existing vote in DB
    mock_db.get.side_effect = lambda model, ident: mock_res if model is LearningResource else mock_uploader
    mock_query = MagicMock()
    mock_query.filter.return_value.first.return_value = None
    mock_db.query.return_value = mock_query

    with patch("backend.api.access.user_class_access"):
        res = vote_resource(resource_id=str(res_id), db=mock_db, current_user=mock_user)
        assert res.helpful_count == 6
        assert res.has_voted is True

    # Second vote: existing vote found -> does not increment again
    mock_query.filter.return_value.first.return_value = ResourceVote(resource_id=res_id, student_id=student_id)
    with patch("backend.api.access.user_class_access"):
        res2 = vote_resource(resource_id=str(res_id), db=mock_db, current_user=mock_user)
        assert res2.helpful_count == 6  # unchanged


def test_report_resource_first_report_counts():
    mock_db = MagicMock()
    res_id = uuid.uuid4()
    mock_user = User(id=uuid.uuid4(), full_name="Alice", role=UserRole.student)
    mock_res = LearningResource(
        id=res_id,
        class_id=uuid.uuid4(),
        topic="Deadlocks",
        title="Spam Link",
        resource_type=ResourceType.youtube,
        status=ReviewStatus.approved,
        report_count=0,
    )

    mock_db.get.return_value = mock_res
    with patch("backend.api.access.user_class_access"):
        res = report_resource(resource_id=str(res_id), db=mock_db, current_user=mock_user)

    assert res["report_count"] == 1
    assert mock_res.report_count == 1
    assert mock_res.status == ReviewStatus.approved
    mock_db.commit.assert_called_once()


def test_report_resource_duplicate_from_same_student_does_not_increment():
    from sqlalchemy.exc import IntegrityError
    mock_db = MagicMock()
    # Simulate flush raising IntegrityError because of unique constraint
    mock_db.flush.side_effect = IntegrityError("duplicate key", {}, None)

    res_id = uuid.uuid4()
    mock_user = User(id=uuid.uuid4(), full_name="Alice", role=UserRole.student)
    mock_res = LearningResource(
        id=res_id,
        class_id=uuid.uuid4(),
        topic="Deadlocks",
        title="Spam Link",
        resource_type=ResourceType.youtube,
        status=ReviewStatus.approved,
        report_count=1,
    )

    mock_db.get.return_value = mock_res
    with patch("backend.api.access.user_class_access"):
        res = report_resource(resource_id=str(res_id), db=mock_db, current_user=mock_user)

    assert res["report_count"] == 1
    assert mock_res.report_count == 1  # Not incremented
    assert mock_res.status == ReviewStatus.approved
    mock_db.commit.assert_not_called()


def test_report_resource_triggers_review_on_threshold():
    mock_db = MagicMock()
    res_id = uuid.uuid4()
    mock_user = User(id=uuid.uuid4(), full_name="Charlie", role=UserRole.student)
    mock_res = LearningResource(
        id=res_id,
        class_id=uuid.uuid4(),
        topic="Deadlocks",
        title="Spam Link",
        resource_type=ResourceType.youtube,
        status=ReviewStatus.approved,
        report_count=2,
    )

    mock_db.get.return_value = mock_res
    with patch("backend.api.access.user_class_access"):
        res = report_resource(resource_id=str(res_id), db=mock_db, current_user=mock_user)

    assert res["report_count"] == 3
    assert mock_res.report_count == 3
    assert mock_res.status == ReviewStatus.pending_review  # Relegated to pending
    mock_db.commit.assert_called_once()


def test_educator_review_resource():
    mock_db = MagicMock()
    res_id = uuid.uuid4()
    educator_id = uuid.uuid4()
    mock_user = User(id=educator_id, full_name="Prof", role=UserRole.educator)
    uploader_id = uuid.uuid4()
    mock_uploader = User(id=uploader_id, full_name="Student Bob", role=UserRole.student)
    mock_res = LearningResource(
        id=res_id,
        class_id=uuid.uuid4(),
        topic="Deadlocks",
        title="Banker's Algorithm notes",
        resource_type=ResourceType.notes,
        status=ReviewStatus.pending_review,
        uploaded_by_id=uploader_id,
        helpful_count=0,
        report_count=0,
    )

    mock_db.get.side_effect = lambda model, ident: mock_res if model is LearningResource else mock_uploader
    payload = schemas.LearningResourceReview(status="approved")

    with patch("backend.api.access.owned_class"):
        res = review_resource(
            resource_id=str(res_id),
            payload=payload,
            db=mock_db,
            current_user=mock_user,
            _educator=None,
        )

    assert res.status == "approved"
    assert mock_res.status == ReviewStatus.approved


def test_resource_upload_rate_limit():
    from backend.core.rate_limit import rate_limit, reset_rate_limits

    reset_rate_limits()
    limiter = rate_limit("resources-upload", max_requests=10, window_seconds=600)

    mock_request = MagicMock()
    mock_request.cookies = {}
    mock_request.client.host = "192.168.1.100"

    # First 10 requests should succeed
    for _ in range(10):
        limiter(mock_request)

    # 11th request should raise 429
    with pytest.raises(HTTPException) as exc:
        limiter(mock_request)
    assert exc.value.status_code == 429
    assert "Too many requests" in exc.value.detail


def test_list_resources_truncation():
    mock_db = MagicMock()
    class_id = uuid.uuid4()
    mock_user = User(id=uuid.uuid4(), full_name="Alice", role=UserRole.student)
    mock_class = Class(id=class_id, name="OS 101")

    res_long = LearningResource(
        id=uuid.uuid4(),
        class_id=class_id,
        topic="Deadlocks",
        title="Comprehensive Deadlock Cheatsheet",
        resource_type=ResourceType.notes,
        content="X" * 650,
        status=ReviewStatus.approved,
        helpful_count=3,
        report_count=0,
        uploaded_by_id=uuid.uuid4(),
        created_at=datetime.now(timezone.utc),
    )
    res_short = LearningResource(
        id=uuid.uuid4(),
        class_id=class_id,
        topic="Deadlocks",
        title="Quick Deadlock Tip",
        resource_type=ResourceType.notes,
        content="Y" * 250,
        status=ReviewStatus.approved,
        helpful_count=1,
        report_count=0,
        uploaded_by_id=uuid.uuid4(),
        created_at=datetime.now(timezone.utc),
    )

    # Mock query chain for list_resources
    # 1. db.query(LearningResource).filter().filter().order_by().offset().limit().all()
    # 2. db.query(ResourceVote.resource_id)...
    # 3. db.query(User)...
    def query_side_effect(model):
        q = MagicMock()
        if model is LearningResource:
            q.filter.return_value = q
            q.order_by.return_value = q
            q.offset.return_value = q
            q.limit.return_value = q
            q.all.return_value = [res_long, res_short]
        elif model is User:
            q.filter.return_value.all.return_value = []
        else:
            q.filter.return_value.all.return_value = []
        return q

    mock_db.query.side_effect = query_side_effect

    with patch("backend.api.access.user_class_access", return_value=mock_class):
        items = list_resources(class_id=str(class_id), db=mock_db, current_user=mock_user)

    assert len(items) == 2

    # Long note: truncated to 500 characters
    assert items[0].content == "X" * 500
    assert items[0].content_length == 650
    assert items[0].truncated is True

    # Short note: untruncated
    assert items[1].content == "Y" * 250
    assert items[1].content_length == 250
    assert items[1].truncated is False


def test_get_resource_returns_full_content():
    mock_db = MagicMock()
    res_id = uuid.uuid4()
    class_id = uuid.uuid4()
    uploader_id = uuid.uuid4()
    student_id = uuid.uuid4()

    mock_user = User(id=student_id, full_name="Alice", role=UserRole.student)
    mock_uploader = User(id=uploader_id, full_name="Bob", role=UserRole.student)
    mock_res = LearningResource(
        id=res_id,
        class_id=class_id,
        topic="Deadlocks",
        title="Full Guide",
        resource_type=ResourceType.notes,
        content="Z" * 750,
        status=ReviewStatus.approved,
        helpful_count=5,
        report_count=0,
        uploaded_by_id=uploader_id,
        created_at=datetime.now(timezone.utc),
    )

    mock_db.get.side_effect = lambda model, ident: mock_res if model is LearningResource else mock_uploader
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with patch("backend.api.access.user_class_access"):
        item = get_resource(resource_id=str(res_id), db=mock_db, current_user=mock_user)

    assert item.content == "Z" * 750
    assert item.content_length == 750
    assert item.truncated is False


def test_get_resource_permissions():
    mock_db = MagicMock()
    res_id = uuid.uuid4()
    class_id = uuid.uuid4()
    uploader_id = uuid.uuid4()
    other_student_id = uuid.uuid4()
    educator_id = uuid.uuid4()

    pending_res = LearningResource(
        id=res_id,
        class_id=class_id,
        topic="Deadlocks",
        title="Pending Notes",
        resource_type=ResourceType.notes,
        content="Draft notes",
        status=ReviewStatus.pending_review,
        helpful_count=0,
        report_count=0,
        uploaded_by_id=uploader_id,
        created_at=datetime.now(timezone.utc),
    )

    uploader_user = User(id=uploader_id, full_name="Owner Student", role=UserRole.student)
    other_student = User(id=other_student_id, full_name="Other Student", role=UserRole.student)
    educator = User(id=educator_id, full_name="Prof", role=UserRole.educator)

    mock_db.get.side_effect = lambda model, ident: pending_res if model is LearningResource else uploader_user
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with patch("backend.api.access.user_class_access"):
        # 1. Other student cannot view another student's pending resource
        with pytest.raises(HTTPException) as exc1:
            get_resource(resource_id=str(res_id), db=mock_db, current_user=other_student)
        assert exc1.value.status_code == 404

        # 2. Uploader student can view their own pending resource
        own_res = get_resource(resource_id=str(res_id), db=mock_db, current_user=uploader_user)
        assert own_res.id == str(res_id)

        # 3. Educator can view any pending resource in their class
        edu_res = get_resource(resource_id=str(res_id), db=mock_db, current_user=educator)
        assert edu_res.id == str(res_id)
