from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any
import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.core import config
from backend.core.tracking_constants import (
    MASTERED_THRESHOLD,
    WEAK_THRESHOLD,
    classify_topic,
)
from backend.models.db import (
    Class,
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
from backend.services import behavior_service, routing_service
from backend.services.topic_grounding_service import (
    TopicGrounding,
    extract_page_number,
    get_topic_grounding,
)

GUIDED_LEARNING_TAGS = {"needs-repetition"}
STALLED_MIN_ATTEMPTS = 2
STALLED_MASTERY_CEILING = WEAK_THRESHOLD


def _normalize_topic_name(topic: str | None) -> str:
    return re.sub(r"[\s-]+", " ", (topic or "").casefold()).strip()


def _resolve_topic_row(
    db: Session,
    subject_id: str | None,
    topic: str,
    topic_id: str | None = None,
) -> PrerequisiteMap | None:
    if not subject_id:
        return None
    if topic_id:
        try:
            row = db.get(PrerequisiteMap, uuid.UUID(str(topic_id)))
        except (ValueError, TypeError, AttributeError):
            row = None
        if row and str(row.subject_id) == str(subject_id):
            return row
    normalized_topic = _normalize_topic_name(topic)
    return next(
        (
            row
            for row in db.query(PrerequisiteMap)
            .filter(PrerequisiteMap.subject_id == subject_id)
            .all()
            if _normalize_topic_name(row.topic) == normalized_topic
        ),
        None,
    )


def _mastery_v2_data(mastery: TopicMastery | None) -> dict[str, Any] | None:
    if not mastery or not mastery.mastery_v2:
        return None
    raw = mastery.mastery_v2
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError) as exc:
        print(f"[RECOMMENDATION WARNING] Invalid mastery_v2 for topic {mastery.topic}: {exc}")
        return None
    if not isinstance(parsed, dict):
        return None
    from backend.services.mastery_v2 import apply_staleness

    return apply_staleness(parsed)


def _curriculum_sections(
    grounding: TopicGrounding,
) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": str(chunk.id),
            "text": chunk.text,
            "similarity": score,
            "document_name": (
                chunk.document.title or chunk.document.filename
                if chunk.document
                else None
            ),
            "page_number": extract_page_number(chunk),
            "section_heading": chunk.section_heading,
        }
        for chunk, score in grounding.chunks
    ]


def _library_resources(
    db: Session, class_id: str, topic: str, subject_name: str | None = None, topic_id: str | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Selects faculty-approved and peer-shared resources strictly scoped to this class.
    Matching Tiers:
      Tier 1: Exact topic match (or explicit topic_id match in content). match_type = "exact"
      Tier 2: Graph relations via PrerequisiteMap (requires, related_concepts, ancestors). match_type = "related"
      Tier 3: Keyword match of topic against resource title/content. match_type = "related"
    Returns best tier first with educator-uploaded resources prioritized.
    Only approved resources from the class are returned (no external search).
    """
    clean_topic = topic.strip()
    topic_lower = clean_topic.lower()

    try:
        class_uuid = uuid.UUID(str(class_id))
    except (ValueError, TypeError, AttributeError):
        class_uuid = class_id

    # Retrieve all approved resources for this class
    approved_rows = (
        db.query(LearningResource, User.role)
        .join(User, LearningResource.uploaded_by_id == User.id)
        .filter(
            LearningResource.class_id == class_uuid,
            LearningResource.status == ReviewStatus.approved,
        )
        .order_by(
            (User.role == UserRole.educator).desc(),
            LearningResource.helpful_count.desc(),
            LearningResource.created_at.desc(),
        )
        .all()
    )

    if not approved_rows:
        return [], []

    # Build graph relations for Tier 2
    from backend.models.db import Class, PrerequisiteMap
    class_row = db.get(Class, class_uuid)
    subject_id = class_row.subject_id if class_row else None

    ancestor_topics: list[str] = []
    related_topic_names: set[str] = set()
    related_topic_ids: set[str] = set()

    if subject_id:
        all_pm = (
            db.query(PrerequisiteMap)
            .filter(PrerequisiteMap.subject_id == subject_id)
            .all()
        )
        pm_by_topic = {p.topic.strip().lower(): p for p in all_pm}
        pm_by_id = {str(p.id): p for p in all_pm}

        # Resolve starting node
        start_node = None
        if topic_id and str(topic_id) in pm_by_id:
            start_node = pm_by_id[str(topic_id)]
        elif topic_lower in pm_by_topic:
            start_node = pm_by_topic[topic_lower]

        if start_node:
            queue = [start_node.topic.strip().lower()]
            visited = set()
            while queue:
                curr = queue.pop(0)
                if curr in visited:
                    continue
                visited.add(curr)
                p = pm_by_topic.get(curr)
                if p:
                    related_topic_ids.add(str(p.id))
                    for relation in (p.requires or []):
                        relation_clean = relation.strip()
                        relation_node = pm_by_id.get(relation_clean) or pm_by_topic.get(relation_clean.lower())
                        relation_name = relation_node.topic.strip() if relation_node else relation_clean
                        relation_key = relation_name.lower()
                        if relation_node:
                            related_topic_ids.add(str(relation_node.id))
                        if relation_key not in visited:
                            ancestor_topics.append(relation_name)
                            related_topic_names.add(relation_key)
                            queue.append(relation_key)
                    for relation in (p.related_concepts or []):
                        relation_clean = relation.strip()
                        relation_node = pm_by_id.get(relation_clean) or pm_by_topic.get(relation_clean.lower())
                        relation_name = relation_node.topic.strip() if relation_node else relation_clean
                        relation_key = relation_name.lower()
                        if relation_node:
                            related_topic_ids.add(str(relation_node.id))
                        if relation_key not in visited:
                            ancestor_topics.append(relation_name)
                            related_topic_names.add(relation_key)

    tier_1_rows: list[tuple[LearningResource, Any, str]] = []
    tier_2_rows: list[tuple[LearningResource, Any, str]] = []
    tier_3_rows: list[tuple[LearningResource, Any, str]] = []

    _STOP = {"and", "the", "for", "with", "from", "into", "that", "this"}

    for r, role in approved_rows:
        r_topic = (r.topic or "").strip().lower()
        r_content = r.content or ""
        r_title = (r.title or "").strip().lower()
        metadata: dict[str, Any] = {}
        if r_content:
            try:
                parsed_content = json.loads(r_content)
                if isinstance(parsed_content, dict):
                    metadata = parsed_content
            except (TypeError, json.JSONDecodeError):
                pass
        resource_topic_id = str(metadata.get("topic_id") or "")

        # Check Tier 1: exact topic match
        is_exact = False
        if r_topic == topic_lower:
            is_exact = True
        elif topic_id and resource_topic_id == str(topic_id):
            is_exact = True

        if is_exact:
            tier_1_rows.append((r, role, "exact"))
            continue

        # Check Tier 2: graph relations
        is_related = False
        if r_topic in related_topic_names:
            is_related = True
        elif resource_topic_id in related_topic_ids:
            is_related = True
        else:
            for anc in ancestor_topics:
                if anc.lower() == r_topic:
                    is_related = True
                    break

        if is_related:
            tier_2_rows.append((r, role, "related"))
            continue

        # Check Tier 3: keyword match of topic against resource title/content
        description = str(metadata.get("description") or "")
        searchable_content = r_content.lower() if not metadata else ""
        searchable_text = f"{r_title} {description.lower()} {searchable_content}"
        if topic_lower in searchable_text:
            tier_3_rows.append((r, role, "related"))
        else:
            words = [
                word for word in re.findall(r"\w+", topic_lower)
                if len(word) > 3 and word not in _STOP
            ]
            if words and any(re.search(rf"\b{re.escape(word)}\b", searchable_text) for word in words):
                tier_3_rows.append((r, role, "related"))

    # Return best tier first
    ranked_rows: list[tuple[LearningResource, Any, str]] = []
    if tier_1_rows:
        ranked_rows.extend(tier_1_rows)
        ranked_rows.extend(tier_2_rows)
        ranked_rows.extend(tier_3_rows)
    elif tier_2_rows:
        def tier2_key(tup):
            res = tup[0]
            t_low = (res.topic or "").lower()
            for idx, anc in enumerate(ancestor_topics):
                if anc.lower() == t_low:
                    return idx
            return 999
        sorted_tier_2 = sorted(tier_2_rows, key=tier2_key)
        ranked_rows.extend(sorted_tier_2)
        ranked_rows.extend(tier_3_rows)
    elif tier_3_rows:
        ranked_rows.extend(tier_3_rows)

    videos: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []

    for r, role, match_type in ranked_rows:
        if r.resource_type == ResourceType.youtube and r.url:
            from backend.services import youtube_service

            meta: dict[str, Any] = {}
            if r.content:
                try:
                    parsed_meta = json.loads(r.content)
                    meta = parsed_meta if isinstance(parsed_meta, dict) else {}
                except (TypeError, json.JSONDecodeError):
                    meta = {}

            # Parse video ID safely from metadata or canonical URL. Never fabricate a fake video ID.
            vid = meta.get("video_id")
            if not vid or not isinstance(vid, str) or len(vid) != 11:
                vid = youtube_service.extract_video_id(r.url)
            if not vid:
                continue

            is_educator = role in (UserRole.educator, UserRole.admin)
            source_tag = meta.get("source") or ("faculty" if is_educator else "student_suggested")
            if source_tag == "auto":
                continue
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
                "topic": r.topic,
                "match_type": match_type,
                "match_reason": (
                    f"Matches this topic: {topic}"
                    if match_type == "exact"
                    else f"Same syllabus area: {r.topic}"
                    if r_topic in related_topic_names and r.topic
                    else f"Approved class resource mentions {topic}"
                ),
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
                "match_type": match_type,
                "match_reason": (
                    f"Matches this topic: {topic}"
                    if match_type == "exact"
                    else f"Approved class notes related to {topic}"
                ),
            })

    unique_videos: list[dict[str, Any]] = []
    seen_video_ids: set[str] = set()
    for video in videos:
        video_id = video["video_id"]
        if video_id in seen_video_ids:
            continue
        seen_video_ids.add(video_id)
        unique_videos.append(video)
        if len(unique_videos) == 3:
            break
    return unique_videos, notes


def _topic_course_documents(
    grounding: TopicGrounding, topic: str
) -> list[dict[str, Any]]:
    """Build ready-document resources only from the shared ranked grounding result."""
    documents: dict[str, dict[str, Any]] = {}
    for chunk, _score in grounding.chunks:
        doc = chunk.document
        if not doc:
            continue
        doc_id = str(doc.id)
        entry = documents.setdefault(
            doc_id,
            {
                "document_id": doc_id,
                "title": doc.title or doc.filename or f"{topic} Course Document",
                "filename": doc.filename,
                "mime_type": doc.mime_type or "application/pdf",
                "page_number": None,
                "excerpt": None,
            },
        )
        if entry["page_number"] is None:
            entry["page_number"] = extract_page_number(chunk)
        if not entry["excerpt"] and chunk.text:
            entry["excerpt"] = chunk.text[:300]

    resources = []
    for entry in documents.values():
        mime = entry["mime_type"]
        format_label = (
            "PDF" if "pdf" in mime.casefold()
            else "Image" if "image" in mime.casefold()
            else "Document"
        )
        page_info = f" · Page {entry['page_number']}" if entry["page_number"] else ""
        doc_id = entry["document_id"]
        resources.append(
            {
                "id": f"doc-{doc_id}",
                "title": entry["title"],
                "resource_type": "notes",
                "document_id": doc_id,
                "file_url": f"/api/v1/documents/{doc_id}/file",
                "content": entry["excerpt"]
                or f"Faculty course document: {entry['filename']} for topic {topic}.",
                "content_snippet": entry["excerpt"],
                "source": "faculty",
                "channel": f"Faculty Document ({format_label}{page_info})",
                "duration": format_label,
                "action": "read",
                "action_label": "Read Document",
                "topic": topic,
                "page_number": entry["page_number"],
                "match_type": "related",
                "match_reason": f"Matched approved curriculum content for {topic}",
            }
        )
    return resources


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
            data = _mastery_v2_data(m)
            if data and data.get("mastery_band") == "low" and data.get("evidence_state") == "sufficient":
                return f"Your mastery on prerequisite '{p}' is low. We recommend strengthening '{p}' before advancing to '{topic}'."
            elif data is None and m.mastery_score < 0.6 and m.attempt_count >= 1:
                return f"Your mastery on prerequisite '{p}' is currently {int(m.mastery_score * 100)}%. Strengthening '{p}' first will help."

    return None


def find_unattempted_prerequisites(
    db: Session,
    student_id: str,
    class_id: str,
    subject_id: str | None,
    topic: str,
) -> list[str]:
    """
    Finds direct prerequisites of `topic` that have never been attempted by the student
    (either no TopicMastery row or attempt_count == 0).
    Only includes prerequisites in the class syllabus vocabulary, compared using normalize_topic_key.
    Returns up to 2 unattempted prerequisites in order. Single DB query for masteries.
    """
    if not subject_id:
        return []

    from backend.core.prerequisites import get_prerequisites_db
    from backend.services.mastery_v2 import normalize_topic_key

    # Fetch syllabus vocabulary for subject
    # All topics registered in PrerequisiteMap for subject_id constitute the syllabus vocabulary
    syllabus_rows = (
        db.query(PrerequisiteMap.topic)
        .filter(PrerequisiteMap.subject_id == subject_id)
        .all()
    )
    syllabus_vocab_keys = {
        normalize_topic_key(r[0])
        for r in syllabus_rows
        if r[0] and normalize_topic_key(r[0])
    }

    # Also include class-level syllabus vocabulary if class exists
    if class_id:
        try:
            from backend.services.progress_service import get_syllabus_topics_for_class
            for t in get_syllabus_topics_for_class(db, class_id):
                k = normalize_topic_key(t)
                if k:
                    syllabus_vocab_keys.add(k)
        except Exception:
            pass

    # Get direct prerequisites
    direct_prereqs = get_prerequisites_db(db, subject_id, topic)
    if not direct_prereqs:
        # Check case-insensitive topic match in PrerequisiteMap if exact match returned nothing
        norm_t = normalize_topic_key(topic)
        pm_rows = db.query(PrerequisiteMap).filter(PrerequisiteMap.subject_id == subject_id).all()
        for r in pm_rows:
            if normalize_topic_key(r.topic) == norm_t and r.requires:
                direct_prereqs = list(r.requires)
                break

    if not direct_prereqs:
        return []

    # Filter direct prerequisites to only those in the class's syllabus vocabulary
    valid_candidates: list[str] = []
    seen_keys: set[str] = set()
    for p in direct_prereqs:
        p_key = normalize_topic_key(p)
        if p_key and p_key in syllabus_vocab_keys and p_key not in seen_keys:
            seen_keys.add(p_key)
            valid_candidates.append(p)

    if not valid_candidates:
        return []

    # Fetch mastery for student & class in ONE query
    student_uuid = uuid.UUID(student_id) if isinstance(student_id, str) else student_id
    class_uuid = uuid.UUID(class_id) if isinstance(class_id, str) else class_id

    mastery_rows = (
        db.query(TopicMastery)
        .filter(
            TopicMastery.student_id == student_uuid,
            TopicMastery.class_id == class_uuid,
        )
        .all()
    )
    mastery_by_key = {}
    for m in mastery_rows:
        mk = normalize_topic_key(m.topic)
        if mk:
            mastery_by_key[mk] = m

    unattempted: list[str] = []
    for p in valid_candidates:
        p_key = normalize_topic_key(p)
        m = mastery_by_key.get(p_key)
        if m is None or (m.attempt_count or 0) == 0:
            unattempted.append(p)
            if len(unattempted) == 2:
                break

    return unattempted


def get_recommendation(
    db: Session,
    student_id: str,
    class_id: str,
    subject_id: str | None,
    topic: str,
    embedding_model: Any,
    topic_id: str | None = None,
) -> dict[str, Any]:
    routing = routing_service.get_topic_routing(db, student_id, class_id, topic)
    learning_tag = behavior_service.get_learning_tag(db, student_id, subject_id, topic) if subject_id else None
    mastery = (
        db.query(TopicMastery)
        .filter(TopicMastery.student_id == student_id, TopicMastery.class_id == class_id, TopicMastery.topic == topic)
        .first()
    )

    settings = config.get_settings()
    v2_data = _mastery_v2_data(mastery) if settings.mastery_v2_enabled else None

    subject_row = db.get(Subject, subject_id) if subject_id else None
    subject_name = subject_row.name if subject_row else None
    topic_row = _resolve_topic_row(db, subject_id, topic, topic_id)
    canonical_topic = topic_row.topic if topic_row else topic.strip()
    resolved_topic_id = str(topic_row.id) if topic_row else None
    grounding = (
        get_topic_grounding(
            db,
            class_id,
            subject_name,
            subject_id,
            canonical_topic,
            topic_row,
            embedding_model,
        )
        if subject_id
        else TopicGrounding([])
    )
    sections = _curriculum_sections(grounding)
    documents = _topic_course_documents(grounding, canonical_topic)

    videos, notes = _library_resources(
        db, class_id, canonical_topic, subject_name, topic_id=resolved_topic_id
    )

    mode = "static"
    reason: str | None = None
    socratic_seed: str | None = None
    prereq_reason: str | None = None

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

    elif settings.mastery_v2_enabled and v2_data is None:
        mode = "initial_assessment"
        reason = f"We do not have current assessment evidence for {topic}. Take an initial assessment to establish your baseline."

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
        elif band == "medium" and evidence == "sufficient":
            if learning_tag in GUIDED_LEARNING_TAGS:
                mode = "ai_session"
                reason = f"You've been asking several follow-up questions about {topic} in chat. Let's work through it in a guided session."
                socratic_seed = topic
            else:
                mode = "reinforce"
                reason = f"You're close on {topic}. A short practice quiz will help lock it in."
        elif mastery is not None and (mastery.attempt_count or 0) > 0:
            print(f"[RECOMMENDATION WARNING] Unexpected mastery combination for {topic}: band={band}, evidence={evidence}. Falling back to diagnostic.")
            mode = "diagnostic"
            reason = f"Let's take a quick check-in quiz on {topic} to calibrate your learning path."
        else:  # completely unattempted
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
        elif mastery is None or (mastery.attempt_count or 0) == 0:
            mode = "initial_assessment"
            reason = f"You haven't attempted {topic} yet. Start with the shared resources below or take an initial quiz."
        else:
            mode = "static"
            reason = None

    prerequisite_advisory: dict[str, Any] | None = None
    if prereq_reason is None:
        unatt = find_unattempted_prerequisites(db, student_id, class_id, subject_id, topic)
        if unatt:
            first_prereq = unatt[0]
            prerequisite_advisory = {
                "topic": first_prereq,
                "reason": f"Before {topic}, it helps to cover {first_prereq}. You haven't attempted it yet.",
                "attempted": False,
            }

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
        "documents": documents,
        "has_material": grounding.has_material,
        "chunk_count": grounding.chunk_count,
        "videos": videos,
        "notes": notes,
        "socratic_seed_message": socratic_seed,
        "prerequisite_advisory": prerequisite_advisory,
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
        db.flush()
        print(f"[OUTCOME TRACKING] Linked attempt {attempt_id} to {linked_count} preceding recommendation(s)")

    return linked_count


def get_progress_recommendations(
    db: Session,
    student_id: str,
    class_id: str,
    embedding_model: Any = None,
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
    developing_topics = []
    insufficient_evidence_topics = []
    strong_topics = []

    for t_name in all_topic_names:
        m = mastery_by_topic.get(t_name)
        v2_info = _mastery_v2_data(m) or {}

        score = m.mastery_score if m else 0.0
        attempts = m.attempt_count if m else 0
        band = v2_info.get("mastery_band", "unknown")
        evidence = v2_info.get("evidence_state", "none")

        category = classify_topic(attempts, evidence, band, score)

        if category == "insufficient":
            insufficient_evidence_topics.append({
                "topic": t_name,
                "topic_id": topic_id_map.get(t_name),
                "mastery_score": score,
                "attempts": attempts,
                "evidence_state": evidence if evidence != "none" else "insufficient",
                "reason": "Needs assessment attempts to evaluate current understanding.",
            })
        elif category == "weak":
            weak_topics.append({
                "topic": t_name,
                "topic_id": topic_id_map.get(t_name),
                "mastery_score": round(score, 2),
                "attempts": attempts,
                "evidence_state": evidence,
                "mastery_band": band,
                "trend": m.trend.value if m else "stable",
            })
        elif category == "developing":
            developing_topics.append({
                "topic": t_name,
                "topic_id": topic_id_map.get(t_name),
                "mastery_score": round(score, 2),
                "attempts": attempts,
                "evidence_state": evidence,
                "mastery_band": band,
                "trend": m.trend.value if m else "stable",
            })
        else:  # strong
            strong_topics.append(t_name)

    # Sort weak topics: lowest mastery first
    weak_topics.sort(key=lambda x: (x["mastery_score"], -x["attempts"]))
    # Sort developing topics: lowest mastery first (ascending)
    developing_topics.sort(key=lambda x: (x["mastery_score"], -x["attempts"]))

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

    def _build_topic_resources(topic_entry: dict[str, Any]) -> dict[str, Any]:
        topic_name = topic_entry["topic"]
        topic_row = _resolve_topic_row(
            db, subject_id, topic_name, topic_entry.get("topic_id")
        )
        topic_id = str(topic_row.id) if topic_row else None
        videos, notes = _library_resources(db, class_id, topic_name, subject_name, topic_id=topic_id)
        grounding = (
            get_topic_grounding(
                db,
                class_id,
                subject_name,
                subject_id,
                topic_row.topic if topic_row else topic_name,
                topic_row,
                embedding_model,
            )
            if subject_id
            else TopicGrounding([])
        )
        course_docs = _topic_course_documents(grounding, topic_name)

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
                "match_type": v.get("match_type", "exact"),
                "match_reason": v.get("match_reason"),
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
                "match_type": n.get("match_type", "exact"),
                "match_reason": f"Approved class notes for {topic_name}",
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
                "match_type": v.get("match_type", "exact"),
                "match_reason": v.get("match_reason"),
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
            "match_reason": f"Practice activity for {topic_name}",
        })

        return {
            "topic": topic_name,
            "topic_id": topic_entry.get("topic_id"),
            "mastery_score": topic_entry["mastery_score"],
            "attempts": topic_entry["attempts"],
            "evidence_state": topic_entry["evidence_state"],
            "mastery_band": topic_entry["mastery_band"],
            "resources": resources_list,
        }

    grouped_recommendations = [_build_topic_resources(wt) for wt in weak_topics]
    grouped_developing = [_build_topic_resources(dt) for dt in developing_topics]

    all_topics_strong = (
        len(grouped_recommendations) == 0
        and len(grouped_developing) == 0
        and len(insufficient_evidence_topics) == 0
        and len(all_topic_names) > 0
    )

    return {
        "class_id": class_id,
        "class_name": class_row.name,
        "subject_id": subject_id,
        "subject_name": subject_name,
        "weak_topics": grouped_recommendations,
        "developing_topics": grouped_developing,
        "insufficient_evidence_topics": insufficient_evidence_topics,
        "all_topics_strong": all_topics_strong,
        "total_tracked_topics": len(all_topic_names),
    }
