from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.api import access
from backend.api.dependencies import CurrentUser, RequireEducator
from backend.core.database import get_db
from backend.core.rate_limit import rate_limit
from backend.models import schemas
from backend.models.db import (
    Class,
    LearningResource,
    ResourceReport,
    ResourceType,
    ResourceVote,
    ReviewStatus,
    User,
    UserRole,
)

import json
from backend.services import youtube_service

router = APIRouter(prefix="/resources", tags=["resources"])

DbDep = Annotated[Session, Depends(get_db)]
ResourceUploadRateLimit = Depends(rate_limit("resources-upload", max_requests=10, window_seconds=600))


def _enrich_read_model(
    r: LearningResource,
    has_voted: bool,
    uploader_name: str | None,
    uploader_role: UserRole | None = None,
    truncate_notes: bool = False,
) -> schemas.LearningResourceRead:
    raw_content = r.content
    content_len = len(raw_content) if raw_content is not None else None
    truncated = False
    display_content = raw_content

    video_id = None
    channel = None
    duration = None
    thumbnail = None
    source = None
    embeddable = True

    topic_id = None
    subject_id = None

    if r.resource_type == ResourceType.youtube:
        parsed_meta: dict[str, Any] | None = None
        if raw_content:
            try:
                parsed_meta = json.loads(raw_content)
            except Exception:
                parsed_meta = None

        if isinstance(parsed_meta, dict):
            video_id = parsed_meta.get("video_id")
            channel = parsed_meta.get("channel")
            duration = parsed_meta.get("duration")
            thumbnail = parsed_meta.get("thumbnail")
            source = parsed_meta.get("source")
            embeddable = parsed_meta.get("embeddable", True)
            topic_id = parsed_meta.get("topic_id")
            subject_id = parsed_meta.get("subject_id")

        if not video_id and r.url:
            video_id = youtube_service.extract_video_id(r.url)

        if not source:
            source = "faculty" if uploader_role in (UserRole.educator, UserRole.admin) else "student_suggested"
        if not thumbnail and video_id:
            thumbnail = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        if not channel:
            channel = "Faculty Approved" if source == "faculty" else "Student Shared"
        display_content = None
    else:
        if truncate_notes and raw_content is not None and len(raw_content) > 500:
            display_content = raw_content[:500]
            truncated = True

    return schemas.LearningResourceRead(
        id=str(r.id),
        class_id=str(r.class_id),
        topic=r.topic,
        topic_id=topic_id,
        subject_id=subject_id,
        title=r.title,
        resource_type=r.resource_type.value,
        url=r.url,
        content=display_content,
        content_length=content_len,
        truncated=truncated,
        status=r.status.value,
        helpful_count=r.helpful_count,
        report_count=r.report_count,
        has_voted=has_voted,
        uploaded_by_id=str(r.uploaded_by_id),
        uploaded_by_name=uploader_name,
        created_at=r.created_at or datetime.now(timezone.utc),
        video_id=video_id,
        channel=channel,
        duration=duration,
        thumbnail=thumbnail,
        source=source,
        embeddable=embeddable,
    )


def _validate_youtube_url(url: str) -> str:
    cleaned = url.strip()
    vid = youtube_service.extract_video_id(cleaned)
    if not vid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid YouTube URL. Please provide a valid youtube.com or youtu.be link.",
        )
    return youtube_service.build_canonical_youtube_url(vid)


@router.post(
    "",
    response_model=schemas.LearningResourceRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[ResourceUploadRateLimit],
)
def create_resource(
    payload: schemas.LearningResourceCreate,
    db: DbDep,
    current_user: CurrentUser,
):
    class_row = access.user_class_access(db, payload.class_id, current_user)

    topic = payload.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic cannot be empty.")

    topic_id = payload.topic_id
    subject_id = str(class_row.subject_id) if class_row.subject_id else None

    # Validate that topic belongs to subject if class has an approved syllabus
    if class_row.subject_id:
        from backend.models.db import PrerequisiteMap

        valid_rows = (
            db.query(PrerequisiteMap)
            .filter(PrerequisiteMap.subject_id == class_row.subject_id)
            .all()
        )
        if valid_rows:
            matching_row = next(
                (
                    r for r in valid_rows
                    if (topic_id and str(r.id) == topic_id) or (r.topic.strip().lower() == topic.lower())
                ),
                None,
            )
            if matching_row is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Topic '{topic}' is not in the approved syllabus for this subject. Please select a valid syllabus topic.",
                )
            topic = matching_row.topic
            topic_id = str(matching_row.id)

    r_type = payload.resource_type.strip().lower()
    if r_type not in (ResourceType.youtube.value, ResourceType.notes.value):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid resource_type '{r_type}'. Allowed: 'youtube', 'notes'.",
        )

    canonical_url = None
    notes_content = None
    title = (payload.title or "").strip()

    if r_type == ResourceType.youtube.value:
        if not payload.url or not payload.url.strip():
            raise HTTPException(status_code=400, detail="YouTube URL is required.")
        video_id = youtube_service.extract_video_id(payload.url)
        if not video_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid YouTube URL. Please provide a valid youtube.com or youtu.be link.",
            )
        video_meta = youtube_service.fetch_youtube_metadata(video_id)
        if not title:
            title = video_meta.get("title") or f"Educational Video ({video_id})"
        source_provenance = (
            "faculty" if current_user.role in (UserRole.educator, UserRole.admin) else "student_suggested"
        )
        video_meta["source"] = source_provenance
        if topic_id:
            video_meta["topic_id"] = topic_id
        if subject_id:
            video_meta["subject_id"] = subject_id
        notes_content = json.dumps(video_meta)
        canonical_url = video_meta.get("url") or youtube_service.build_canonical_youtube_url(video_id)
    else:
        if not title:
            raise HTTPException(status_code=400, detail="Title cannot be empty.")
        if not payload.content or not payload.content.strip():
            raise HTTPException(status_code=400, detail="Notes content is required.")
        if len(payload.content) > 50_000:
            raise HTTPException(
                status_code=413,
                detail="Notes content exceeds the 50,000 character limit.",
            )
        notes_content = payload.content.strip()

    initial_status = (
        ReviewStatus.approved
        if current_user.role in (UserRole.educator, UserRole.admin)
        else ReviewStatus.pending_review
    )

    resource = LearningResource(
        class_id=class_row.id,
        topic=topic,
        title=title,
        resource_type=ResourceType(r_type),
        url=canonical_url,
        content=notes_content,
        status=initial_status,
        helpful_count=0,
        report_count=0,
        uploaded_by_id=current_user.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(resource)
    db.commit()
    db.refresh(resource)

    return _enrich_read_model(
        resource,
        has_voted=False,
        uploader_name=current_user.full_name,
        uploader_role=current_user.role,
    )


@router.get("", response_model=list[schemas.LearningResourceRead])
def list_resources(
    class_id: str,
    db: DbDep,
    current_user: CurrentUser,
    topic: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    class_row = access.user_class_access(db, class_id, current_user)

    query = db.query(LearningResource).filter(LearningResource.class_id == class_row.id)

    is_educator = current_user.role in (UserRole.educator, UserRole.admin)
    if not is_educator:
        query = query.filter(LearningResource.status == ReviewStatus.approved)
    elif isinstance(status_filter, str) and status_filter.strip():
        try:
            target_status = ReviewStatus(status_filter.strip().lower())
            query = query.filter(LearningResource.status == target_status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status '{status_filter}'.")

    if isinstance(topic, str) and topic.strip():
        query = query.filter(LearningResource.topic == topic.strip())

    limit_val = limit if isinstance(limit, int) else 50
    offset_val = offset if isinstance(offset, int) else 0

    resources = (
        query.order_by(
            LearningResource.status == ReviewStatus.approved,
            LearningResource.helpful_count.desc(),
            LearningResource.created_at.desc(),
        )
        .offset(offset_val)
        .limit(limit_val)
        .all()
    )

    if not resources:
        return []

    resource_ids = [r.id for r in resources]
    voted_ids = {
        row.resource_id
        for row in db.query(ResourceVote.resource_id)
        .filter(
            ResourceVote.resource_id.in_(resource_ids),
            ResourceVote.student_id == current_user.id,
        )
        .all()
    }

    uploader_ids = {r.uploaded_by_id for r in resources}
    uploaders = {u.id: u.full_name for u in db.query(User).filter(User.id.in_(uploader_ids)).all()}

    uploader_roles = {u.id: u.role for u in db.query(User).filter(User.id.in_(uploader_ids)).all()}

    return [
        _enrich_read_model(
            r,
            has_voted=r.id in voted_ids,
            uploader_name=uploaders.get(r.uploaded_by_id),
            uploader_role=uploader_roles.get(r.uploaded_by_id),
            truncate_notes=True,
        )
        for r in resources
    ]


@router.get("/{resource_id}", response_model=schemas.LearningResourceRead)
def get_resource(
    resource_id: str,
    db: DbDep,
    current_user: CurrentUser,
):
    resource_uuid = access.parse_uuid(resource_id, "Resource")
    resource = db.get(LearningResource, resource_uuid)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found.")

    access.user_class_access(db, resource.class_id, current_user)

    is_educator = current_user.role in (UserRole.educator, UserRole.admin)
    if not is_educator and resource.status != ReviewStatus.approved and resource.uploaded_by_id != current_user.id:
        raise HTTPException(status_code=404, detail="Resource not found.")

    has_voted = (
        db.query(ResourceVote.id)
        .filter(
            ResourceVote.resource_id == resource.id,
            ResourceVote.student_id == current_user.id,
        )
        .first()
        is not None
    )

    uploader = db.get(User, resource.uploaded_by_id)

    return _enrich_read_model(
        resource,
        has_voted=has_voted,
        uploader_name=uploader.full_name if uploader else None,
        uploader_role=uploader.role if uploader else None,
    )


@router.post("/{resource_id}/vote", response_model=schemas.LearningResourceRead)
def vote_resource(
    resource_id: str,
    db: DbDep,
    current_user: CurrentUser,
):
    resource_uuid = access.parse_uuid(resource_id, "Resource")
    resource = db.get(LearningResource, resource_uuid)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found.")

    access.user_class_access(db, resource.class_id, current_user)

    existing_vote = (
        db.query(ResourceVote)
        .filter(ResourceVote.resource_id == resource.id, ResourceVote.student_id == current_user.id)
        .first()
    )
    if existing_vote is None:
        db.add(ResourceVote(resource_id=resource.id, student_id=current_user.id, vote_type="helpful"))
        resource.helpful_count += 1
        db.commit()
        db.refresh(resource)

    uploader = db.get(User, resource.uploaded_by_id)

    return _enrich_read_model(
        resource,
        has_voted=True,
        uploader_name=uploader.full_name if uploader else None,
        uploader_role=uploader.role if uploader else None,
    )


@router.post("/{resource_id}/report")
def report_resource(
    resource_id: str,
    db: DbDep,
    current_user: CurrentUser,
):
    resource_uuid = access.parse_uuid(resource_id, "Resource")
    resource = db.get(LearningResource, resource_uuid)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found.")

    access.user_class_access(db, resource.class_id, current_user)

    inserted = False
    try:
        with db.begin_nested():
            db.add(ResourceReport(resource_id=resource.id, student_id=current_user.id))
            db.flush()
            inserted = True
    except IntegrityError:
        inserted = False

    if inserted:
        resource.report_count += 1
        if resource.report_count >= 3 and resource.status == ReviewStatus.approved:
            resource.status = ReviewStatus.pending_review
        db.commit()

    return {"message": "Resource reported for review.", "report_count": resource.report_count}


@router.patch("/{resource_id}/review", response_model=schemas.LearningResourceRead)
def review_resource(
    resource_id: str,
    payload: schemas.LearningResourceReview,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    resource_uuid = access.parse_uuid(resource_id, "Resource")
    resource = db.get(LearningResource, resource_uuid)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found.")

    access.owned_class(db, resource.class_id, current_user)

    new_status = payload.status.strip().lower()
    if new_status not in (ReviewStatus.approved.value, ReviewStatus.rejected.value):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid review status '{new_status}'. Allowed: 'approved', 'rejected'.",
        )

    resource.status = ReviewStatus(new_status)
    db.commit()
    db.refresh(resource)

    uploader = db.get(User, resource.uploaded_by_id)

    return _enrich_read_model(
        resource,
        has_voted=False,
        uploader_name=uploader.full_name if uploader else None,
        uploader_role=uploader.role if uploader else None,
    )
