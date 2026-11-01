from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any
import uuid

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.core import config
from backend.models.db import (
    Chunk,
    Class,
    Document,
    LearningResource,
    MasteryTrend,
    PrerequisiteMap,
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
    db: Session, class_id: str, topic: str, subject_name: str | None = None, topic_id: str | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Selects faculty-approved and peer-shared resources from the library for this topic and class.
    Ranking order:
      1. Educator-uploaded resources first (source: 'faculty')
      2. Approved student-shared resources (source: 'student_suggested')
      3. Helpful count descending
      4. Recency descending
      5. Automatically discovered YouTube candidates when no approved videos exist (source: 'auto')
    """
    clean_topic = topic.strip()
    topic_filters = [
        func.lower(func.trim(LearningResource.topic)) == func.lower(clean_topic)
    ]
    if topic_id:
        topic_filters.append(LearningResource.content.ilike(f'%"topic_id": "{topic_id}"%'))

    try:
        class_uuid = uuid.UUID(str(class_id))
    except (ValueError, TypeError, AttributeError):
        class_uuid = class_id

    rows = (
        db.query(LearningResource, User.role)
        .join(User, LearningResource.uploaded_by_id == User.id)
        .filter(
            LearningResource.class_id == class_uuid,
            or_(*topic_filters),
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
            from backend.services import youtube_service

            meta: dict[str, Any] = {}
            if r.content:
                try:
                    meta = json.loads(r.content)
                except Exception:
                    meta = {}

            # Parse video ID safely from metadata or canonical URL. Never fabricate a fake video ID.
            vid = meta.get("video_id")
            if not vid or not isinstance(vid, str) or len(vid) != 11:
                vid = youtube_service.extract_video_id(r.url)

            is_educator = role in (UserRole.educator, UserRole.admin)
            source_tag = meta.get("source") or ("faculty" if is_educator else "student_suggested")
            channel_name = meta.get("channel") or ("Faculty Approved" if is_educator else "Student Shared")
            thumb = meta.get("thumbnail") or (f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else None)

            videos.append({
                "video_id": vid,
                "title": r.title or meta.get("title", f"Video ({vid})" if vid else "Educational Video"),
                "channel": channel_name,
                "duration": meta.get("duration", "Video"),
                "thumbnail": thumb,
                "source": source_tag,
                "embeddable": meta.get("embeddable", True),
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

    # When no curated or approved student videos exist, discover automatic candidates
    if not videos:
        from backend.services import youtube_service
        auto_videos = youtube_service.discover_topic_videos(topic, subject_name)
        videos.extend(auto_videos)

    return videos, notes


def _topic_course_documents(
    db: Session, class_id: str, topic: str, topic_id: str | None = None
) -> list[dict[str, Any]]:
    """Retrieves faculty course documents strictly scoped to this class that have reliable topic association."""
    clean_topic = topic.strip()
    docs_found: dict[uuid.UUID, dict[str, Any]] = {}

    try:
        class_uuid = uuid.UUID(str(class_id))
    except (ValueError, TypeError, AttributeError):
        return []

    # Source 1: Check canonical PrerequisiteMap for source_document_id
    topic_row = None
    if topic_id:
        try:
            topic_row = db.get(PrerequisiteMap, uuid.UUID(str(topic_id)))
        except (ValueError, TypeError, AttributeError):
            topic_row = None

    if not topic_row:
        class_row = db.get(Class, class_uuid)
        if class_row and class_row.subject_id:
            topic_row = (
                db.query(PrerequisiteMap)
                .filter(
                    PrerequisiteMap.subject_id == class_row.subject_id,
                    func.lower(func.trim(PrerequisiteMap.topic)) == func.lower(clean_topic),
                )
                .first()
            )

    if topic_row and topic_row.source_document_id:
        doc = (
            db.query(Document)
            .filter(
                Document.id == topic_row.source_document_id,
                Document.class_id == class_uuid,
                Document.deleted == False,  # noqa: E712
            )
            .first()
        )
        if doc:
            docs_found[doc.id] = {
                "document_id": str(doc.id),
                "title": doc.title or f"{clean_topic} Course Notes",
                "filename": doc.filename,
                "mime_type": doc.mime_type or "application/pdf",
                "page_number": topic_row.source_page_number,
                "excerpt": None,
            }

    # Source 2: Chunks explicitly tagged with this topic in this class
    chunk_rows = (
        db.query(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .filter(
            Document.class_id == class_uuid,
            Document.deleted == False,  # noqa: E712
            func.lower(func.trim(Chunk.topic)) == func.lower(clean_topic),
        )
        .order_by(Chunk.chunk_index)
        .limit(5)
        .all()
    )

    for chunk, doc in chunk_rows:
        if doc.id not in docs_found:
            docs_found[doc.id] = {
                "document_id": str(doc.id),
                "title": doc.title or f"{clean_topic} Course Document",
                "filename": doc.filename,
                "mime_type": doc.mime_type or "application/pdf",
                "page_number": chunk.page_number,
                "excerpt": chunk.text[:300] if chunk.text else None,
            }
        elif not docs_found[doc.id].get("excerpt") and chunk.text:
            docs_found[doc.id]["excerpt"] = chunk.text[:300]

    result = []
    for d in docs_found.values():
        doc_id = d["document_id"]
        mime = d.get("mime_type") or "Document"
        format_label = "PDF" if "pdf" in mime.lower() else "Image" if "image" in mime.lower() else "Document"
        page_info = f" · Page {d['page_number']}" if d.get("page_number") else ""
        result.append({
            "id": f"doc-{doc_id}",
            "title": d["title"],
            "resource_type": "notes",
            "document_id": doc_id,
            "file_url": f"/api/v1/documents/{doc_id}/file",
            "content": d.get("excerpt") or f"Faculty course document: {d.get('filename', 'document')} for topic {clean_topic}.",
            "content_snippet": d.get("excerpt"),
            "source": "faculty",
            "channel": f"Faculty Document ({format_label}{page_info})",
            "duration": format_label,
            "action": "read",
            "action_label": "Read Document",
            "topic": clean_topic,
        })
    return result


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
    subject_row = db.get(Subject, subject_id) if subject_id else None
    subject_name = subject_row.name if subject_row else None
    videos, notes = _library_resources(db, class_id, topic, subject_name)

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


def get_progress_recommendations(
    db: Session,
    student_id: str,
    class_id: str,
) -> dict[str, Any]:
    """
    Computes personalized learning recommendations for the student Progress page
    based on empirical assessment performance.
    Identifies weak topics, gathers prioritized multi-modal resources, and distinguishes
    topics with insufficient evidence.
    """
    from backend.models.db import Class, PrerequisiteMap, Quiz, QuizQuestion, ReviewStatus, Subject, TopicMastery

    class_row = db.get(Class, class_id)
    if not class_row:
        raise ValueError(f"Class '{class_id}' not found.")

    subject_id = str(class_row.subject_id) if class_row.subject_id else None
    subject_row = db.get(Subject, class_row.subject_id) if subject_id else None
    subject_name = subject_row.name if subject_row else (class_row.subject or "Current Subject")

    # Fetch all topic masteries for this student in this class
    mastery_rows = (
        db.query(TopicMastery)
        .filter(TopicMastery.student_id == student_id, TopicMastery.class_id == class_id)
        .all()
    )
    mastery_by_topic = {m.topic: m for m in mastery_rows}

    # Fetch syllabus topics if available
    syllabus_topic_rows = []
    if subject_id:
        syllabus_topic_rows = (
            db.query(PrerequisiteMap)
            .filter(PrerequisiteMap.subject_id == class_row.subject_id)
            .order_by(PrerequisiteMap.created_at, PrerequisiteMap.topic)
            .all()
        )
    topic_id_map = {r.topic: str(r.id) for r in syllabus_topic_rows}

    # All tracked or syllabus topics
    all_topic_names = set(mastery_by_topic.keys())
    for st in syllabus_topic_rows:
        all_topic_names.add(st.topic)

    weak_topics = []
    insufficient_evidence_topics = []
    strong_topics = []

    for t_name in all_topic_names:
        m = mastery_by_topic.get(t_name)
        v2_info = {}
        if m and m.mastery_v2:
            try:
                v2_info = json.loads(m.mastery_v2) if isinstance(m.mastery_v2, str) else m.mastery_v2
            except Exception:
                v2_info = {}

        score = m.mastery_score if m else 0.0
        attempts = m.attempt_count if m else 0
        band = v2_info.get("mastery_band", "unknown")
        evidence = v2_info.get("evidence_state", "none")

        if attempts == 0 or evidence in ("none", "insufficient"):
            insufficient_evidence_topics.append({
                "topic": t_name,
                "topic_id": topic_id_map.get(t_name),
                "mastery_score": score,
                "attempts": attempts,
                "evidence_state": evidence if evidence != "none" else "insufficient",
                "reason": "Needs assessment attempts to evaluate current understanding.",
            })
        elif band == "low" or score < 0.60:
            weak_topics.append({
                "topic": t_name,
                "topic_id": topic_id_map.get(t_name),
                "mastery_score": round(score, 2),
                "attempts": attempts,
                "evidence_state": evidence,
                "mastery_band": band,
                "trend": m.trend.value if m else "stable",
            })
        elif band == "high" or score >= 0.70:
            strong_topics.append(t_name)

    # Sort weak topics: lowest mastery first
    weak_topics.sort(key=lambda x: (x["mastery_score"], -x["attempts"]))

    # Find available quizzes in this class for practice actions (exclude topic practice quizzes)
    approved_quizzes = (
        db.query(Quiz)
        .filter(
            Quiz.class_id == class_id,
            Quiz.status == ReviewStatus.approved,
            or_(Quiz.generation_type.is_(None), Quiz.generation_type != "topic_practice"),
        )
        .all()
    )
    quiz_by_topic: dict[str, str] = {}
    general_quiz_id = str(approved_quizzes[0].id) if approved_quizzes else None

    for q in approved_quizzes:
        for q_question in q.questions:
            if q_question.status == ReviewStatus.approved and q_question.topic and q_question.topic not in quiz_by_topic:
                quiz_by_topic[q_question.topic] = str(q.id)

    # Build resource recommendations for each weak topic
    grouped_recommendations = []
    for wt in weak_topics:
        topic_name = wt["topic"]
        topic_id = wt.get("topic_id")
        videos, notes = _library_resources(db, class_id, topic_name, subject_name, topic_id=topic_id)
        course_docs = _topic_course_documents(db, class_id, topic_name, topic_id=topic_id)

        resources_list = []

        # 1. Faculty-curated YouTube videos first
        faculty_videos = [v for v in videos if v.get("source") == "faculty"]
        for v in faculty_videos:
            resources_list.append({
                "id": v.get("video_id") or v.get("url") or str(uuid.uuid4()),
                "video_id": v.get("video_id"),
                "title": v.get("title", f"{topic_name} Lecture"),
                "resource_type": "youtube",
                "url": v.get("url"),
                "source": "faculty",
                "channel": v.get("channel", "Faculty Approved"),
                "duration": v.get("duration", "Video"),
                "thumbnail": v.get("thumbnail"),
                "action": "watch",
                "action_label": "Watch Video",
                "topic": topic_name,
            })

        # 2. Faculty notes & course documents
        # 2a. Reliable faculty-uploaded course documents / syllabus materials
        for cd in course_docs:
            resources_list.append(cd)

        # 2b. Faculty-curated text notes
        for n in notes:
            resources_list.append({
                "id": n.get("resource_id"),
                "title": n.get("title", f"{topic_name} Notes"),
                "resource_type": "notes",
                "content": n.get("content", ""),
                "content_snippet": n.get("content", "")[:240] if n.get("content") else None,
                "source": "faculty" if n.get("author_role") in ("educator", "admin") else "peer",
                "channel": "Faculty Material" if n.get("author_role") in ("educator", "admin") else "Class Notes",
                "duration": f"{n.get('content_length', 0)} chars",
                "action": "read",
                "action_label": "Read Notes",
                "topic": topic_name,
            })

        # 3. Approved student-suggested videos
        student_videos = [v for v in videos if v.get("source") == "student_suggested"]
        for v in student_videos:
            resources_list.append({
                "id": v.get("video_id") or v.get("url") or str(uuid.uuid4()),
                "video_id": v.get("video_id"),
                "title": v.get("title", f"{topic_name} Student Recommendation"),
                "resource_type": "youtube",
                "url": v.get("url"),
                "source": "student_suggested",
                "channel": v.get("channel", "Community Shared"),
                "duration": v.get("duration", "Video"),
                "thumbnail": v.get("thumbnail"),
                "action": "watch",
                "action_label": "Watch Video",
                "topic": topic_name,
            })

        # 4. Validated auto-discovered videos (if no faculty/student video)
        if not faculty_videos and not student_videos:
            auto_videos = [v for v in videos if v.get("source") == "auto"]
            for v in auto_videos[:2]:
                resources_list.append({
                    "id": v.get("video_id") or v.get("url") or str(uuid.uuid4()),
                    "video_id": v.get("video_id"),
                    "title": v.get("title", f"{topic_name} Video"),
                    "resource_type": "youtube",
                    "url": v.get("url"),
                    "source": "auto",
                    "channel": v.get("channel", "YouTube Educational"),
                    "duration": v.get("duration", "Video"),
                    "thumbnail": v.get("thumbnail"),
                    "action": "watch",
                    "action_label": "Watch Video",
                    "topic": topic_name,
                })

        # 5. Practice activity / Topic quiz for follow-up (always provide at least practice action)
        practise_quiz_id = quiz_by_topic.get(topic_name) or general_quiz_id
        quiz_url = f"/quiz/{practise_quiz_id}" if practise_quiz_id else "/quiz"
        resources_list.append({
            "id": f"quiz-{practise_quiz_id or 'practice'}-{topic_name}",
            "title": f"Practice Quiz: {topic_name}",
            "resource_type": "quiz",
            "url": quiz_url,
            "source": "system",
            "channel": "Assessment Practice",
            "duration": "Quick Quiz",
            "action": "practise",
            "action_label": "Take Quiz",
            "topic": topic_name,
        })

        grouped_recommendations.append({
            "topic": topic_name,
            "topic_id": wt.get("topic_id"),
            "mastery_score": wt["mastery_score"],
            "attempts": wt["attempts"],
            "evidence_state": wt["evidence_state"],
            "mastery_band": wt["mastery_band"],
            "resources": resources_list,
        })

    return {
        "class_id": class_id,
        "class_name": class_row.name,
        "subject_id": subject_id,
        "subject_name": subject_name,
        "weak_topics": grouped_recommendations,
        "insufficient_evidence_topics": insufficient_evidence_topics,
        "all_topics_strong": len(grouped_recommendations) == 0 and len(strong_topics) > 0,
        "total_tracked_topics": len(all_topic_names),
    }

