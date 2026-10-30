from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any

from sqlalchemy.orm import Session

from backend.core import config
from backend.models.db import (
    Chunk,
    Document,
    LearningResource,
    MasteryTrend,
    RecommendationLog,
    ResourceType,
    ReviewStatus,
    Subject,
    TopicMastery,
    User,
    UserRole,
)
from backend.services import behavior_service, routing_service, topic_graph_service

GUIDED_LEARNING_TAGS = {"needs-repetition"}
STALLED_MIN_ATTEMPTS = 2
STALLED_MASTERY_CEILING = 0.6


def _curriculum_sections(
    db: Session, class_id: str, subject_id: str, topic: str, embedding_model: Any, top_k: int = 5
) -> list[dict[str, Any]]:
    names, vectors = topic_graph_service.topic_anchors(db, subject_id, embedding_model)
    if topic not in names:
        return []
    anchor_vector = vectors[names.index(topic)]

    distance_expr = Chunk.embedding.cosine_distance(anchor_vector)
    rows = (
        db.query(Chunk, distance_expr.label("distance"))
        .join(Document, Chunk.document_id == Document.id)
        .filter(
            Document.class_id == class_id,
            Document.deleted == False,  # noqa: E712
            Chunk.subject_id == subject_id,
            Chunk.topic == topic,
        )
        .order_by(distance_expr)
        .limit(top_k)
        .all()
    )
    return [{"chunk_id": str(chunk.id), "text": chunk.text, "similarity": 1 - distance} for chunk, distance in rows]


def _library_resources(
    db: Session, class_id: str, topic: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Selects faculty-approved and peer-shared resources from the library for this topic and class.
    Ranking order:
      1. Educator-uploaded resources first
      2. Helpful count descending
      3. Recency descending
    """
    rows = (
        db.query(LearningResource, User.role)
        .join(User, LearningResource.uploaded_by_id == User.id)
        .filter(
            LearningResource.class_id == class_id,
            LearningResource.topic == topic,
            LearningResource.status == ReviewStatus.approved,
        )
        .order_by(
            (User.role == UserRole.educator).desc(),
            LearningResource.helpful_count.desc(),
            LearningResource.created_at.desc(),
        )
        .all()
    )

    videos: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []

    for r, role in rows:
        if r.resource_type == ResourceType.youtube and r.url:
            match = re.search(r"(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{11})", r.url)
            vid = match.group(1) if match else str(r.id)
            videos.append({
                "video_id": vid,
                "title": r.title,
                "channel": "Faculty Approved" if role == UserRole.educator else "Student Shared",
                "url": r.url,
                "helpful_count": r.helpful_count,
            })
        elif r.resource_type == ResourceType.notes and r.content:
            raw_content = r.content
            content_length = len(raw_content)
            truncated = content_length > 500
            notes.append({
                "resource_id": str(r.id),
                "title": r.title,
                "content": raw_content[:500] if truncated else raw_content,
                "content_length": content_length,
                "truncated": truncated,
                "author_role": role.value if hasattr(role, "value") else str(role),
                "helpful_count": r.helpful_count,
            })

    return videos, notes


def _check_prerequisite_gap(
    db: Session, student_id: str, class_id: str, subject_id: str | None, topic: str
) -> str | None:
    """
    Inspects whether any prerequisite for this topic has an open misconception or low mastery.
    """
    if not subject_id:
        return None
    from backend.core.prerequisites import get_prerequisites_db

    prereqs = get_prerequisites_db(db, subject_id, topic)
    if not prereqs:
        return None

    # Check for open misconceptions on any prerequisite
    intervene = routing_service.intervene_topics(db, student_id, class_id)
    for p in prereqs:
        if p in intervene:
            return f"Prerequisite '{p}' has an unresolved misconception. Resolving it first will make '{topic}' much easier to master."

    # Check mastery on prerequisites
    prereq_masteries = {
        m.topic: m
        for m in db.query(TopicMastery).filter(
            TopicMastery.student_id == student_id,
            TopicMastery.class_id == class_id,
            TopicMastery.topic.in_(prereqs),
        ).all()
    }

    for p in prereqs:
        m = prereq_masteries.get(p)
        if m is not None:
            if m.mastery_v2:
                try:
                    data = json.loads(m.mastery_v2)
                    from backend.services.mastery_v2 import apply_staleness
                    data = apply_staleness(data)
                    if data.get("mastery_band") == "low" and data.get("evidence_state") == "sufficient":
                        return f"Your mastery on prerequisite '{p}' is low. We recommend strengthening '{p}' before advancing to '{topic}'."
                except Exception:
                    pass
            elif m.mastery_score < 0.6 and m.attempt_count >= 1:
                return f"Your mastery on prerequisite '{p}' is currently {int(m.mastery_score * 100)}%. Strengthening '{p}' first will help."

    return None


def get_recommendation(
    db: Session,
    student_id: str,
    class_id: str,
    subject_id: str | None,
    topic: str,
    embedding_model: Any,
) -> dict[str, Any]:
    routing = routing_service.get_topic_routing(db, student_id, class_id, topic)
    learning_tag = behavior_service.get_learning_tag(db, student_id, subject_id, topic) if subject_id else None
    mastery = (
        db.query(TopicMastery)
        .filter(TopicMastery.student_id == student_id, TopicMastery.class_id == class_id, TopicMastery.topic == topic)
        .first()
    )

    settings = config.get_settings()
    v2_data: dict[str, Any] | None = None
    if settings.mastery_v2_enabled and mastery and mastery.mastery_v2:
        try:
            v2_data = json.loads(mastery.mastery_v2)
            from backend.services.mastery_v2 import apply_staleness
            v2_data = apply_staleness(v2_data)
        except Exception:
            v2_data = None

    # Retrieve peer resources from internal library and curriculum sections
    sections: list[dict[str, Any]] = []
    if subject_id and embedding_model:
        sections = _curriculum_sections(db, class_id, subject_id, topic, embedding_model)
    videos, notes = _library_resources(db, class_id, topic)

    mode = "static"
    reason: str | None = None
    socratic_seed: str | None = None

    # Step 1: Open misconception takes highest priority
    if routing == routing_service.INTERVENE:
        mode = "ai_session"
        reason = "There's an open misconception on this topic. A guided session will unlock it for quizzes again."
        socratic_seed = topic

    # Step 2: Prerequisite blocking gap check
    elif (prereq_reason := _check_prerequisite_gap(db, student_id, class_id, subject_id, topic)) is not None:
        mode = "ai_session"
        reason = prereq_reason
        socratic_seed = topic

    # Step 3: Mastery v2 Evidence-State Decision Ladder
    elif v2_data is not None:
        evidence = v2_data.get("evidence_state", "none")
        band = v2_data.get("mastery_band", "unknown")

        if band == "low" and evidence == "sufficient":
            mode = "ai_session"
            reason = f"Your quiz attempts show persistent difficulty with {topic}. Let's work through it together in a guided session."
            socratic_seed = topic
        elif band in ("low", "medium") and evidence == "insufficient":
            mode = "diagnostic"
            reason = f"We have limited quiz data on {topic}. A quick diagnostic quiz will pinpoint what to focus on next."
        elif band == "high" and evidence == "insufficient":
            mode = "verification"
            reason = f"You are doing well on {topic}, but we need a few more questions to verify consistent mastery."
        elif band == "high" and evidence == "sufficient":
            mode = "advance"
            reason = f"You have demonstrated solid mastery of {topic}! Explore advanced resources or proceed to the next unit."
        else:  # unknown or none
            mode = "initial_assessment"
            reason = f"You haven't attempted {topic} yet. Start with the shared resources below or take an initial quiz."

    # Step 4: Fallback to v1 Logic (when v2 is absent or disabled)
    else:
        stalled = (
            mastery is not None
            and (mastery.attempt_count or 0) >= STALLED_MIN_ATTEMPTS
            and (mastery.mastery_score or 0.0) < STALLED_MASTERY_CEILING
            and mastery.trend in (MasteryTrend.stable, MasteryTrend.declining)
        )
        if learning_tag in GUIDED_LEARNING_TAGS:
            mode = "ai_session"
            reason = "You've been coming back to this topic, so a step-by-step guided session should help."
            socratic_seed = topic
        elif stalled:
            mode = "ai_session"
            reason = "Your scores on this topic haven't moved after a few attempts, so let's work through it together."
            socratic_seed = topic
        else:
            mode = "static"
            reason = None

    rec_id: str | None = None
    if mode != "static":
        try:
            cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
            existing_log = (
                db.query(RecommendationLog)
                .filter(
                    RecommendationLog.student_id == student_id,
                    RecommendationLog.class_id == class_id,
                    RecommendationLog.topic == topic,
                    RecommendationLog.mode == mode,
                    RecommendationLog.outcome_attempt_id.is_(None),
                    RecommendationLog.created_at >= cutoff,
                )
                .order_by(RecommendationLog.created_at.desc())
                .first()
            )
            if existing_log is not None:
                rec_id = str(existing_log.id)
            else:
                rec_log = RecommendationLog(
                    student_id=student_id,
                    class_id=class_id,
                    topic=topic,
                    mode=mode,
                    reason=reason,
                    outcome_score_before=mastery.mastery_score if mastery is not None else None,
                )
                db.add(rec_log)
                db.commit()
                db.refresh(rec_log)
                rec_id = str(rec_log.id)
        except Exception as exc:
            db.rollback()
            print(f"[RECOMMENDATION WARNING] Failed to persist recommendation log: {exc}")

    return {
        "id": rec_id,
        "routing": routing,
        "learning_tag": learning_tag,
        "mode": mode,
        "reason": reason,
        "sections": sections,
        "videos": videos,
        "notes": notes,
        "socratic_seed_message": socratic_seed,
    }


def link_quiz_attempt_to_recommendations(
    db: Session,
    student_id: str,
    class_id: str,
    attempt_id: str,
    topic_scores: dict[str, float],
    updated_mastery: dict[str, Any] | None = None,
) -> int:
    """
    Associates a newly completed quiz attempt with any recent unlinked recommendations
    for the tested topics, recording the score outcome delta.
    """
    if not updated_mastery:
        return 0

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
    linked_count = 0

    for topic in topic_scores.keys():
        mastery_info = updated_mastery.get(topic)
        if not isinstance(mastery_info, dict) or "mastery_score" not in mastery_info:
            continue

        after_score = float(mastery_info["mastery_score"])

        rec_log = (
            db.query(RecommendationLog)
            .filter(
                RecommendationLog.student_id == student_id,
                RecommendationLog.class_id == class_id,
                RecommendationLog.topic == topic,
                RecommendationLog.outcome_attempt_id.is_(None),
                RecommendationLog.created_at >= cutoff,
            )
            .order_by(RecommendationLog.created_at.desc())
            .first()
        )
        if rec_log is not None:
            rec_log.outcome_attempt_id = attempt_id
            rec_log.outcome_score_after = after_score
            if rec_log.outcome_score_before is not None:
                rec_log.outcome_delta = round(after_score - float(rec_log.outcome_score_before), 4)
            else:
                rec_log.outcome_delta = None
            linked_count += 1

    if linked_count > 0:
        db.commit()
        print(f"[OUTCOME TRACKING] Linked attempt {attempt_id} to {linked_count} preceding recommendation(s)")

    return linked_count

