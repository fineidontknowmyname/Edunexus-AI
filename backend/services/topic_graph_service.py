from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.models.db import (
    Chunk,
    Class,
    InteractionPattern,
    LearningResource,
    Misconception,
    MisconceptionRule,
    PrerequisiteMap,
    Quiz,
    QuizAttempt,
    QuizAttemptAnswer,
    QuizQuestion,
    RecommendationLog,
    Reflection,
    Subject,
    TopicBehavior,
    TopicMastery,
    VideoRecommendationCache,
)
from backend.services.mastery_v2 import normalize_topic_key
from backend.services.progress_service import (
    _topic_score_history,
    calculate_mastery,
    calculate_trend,
)

HANDLED_TOPIC_COLUMNS: set[tuple[str, str]] = {
    ("prerequisite_map", "topic"),
    ("topic_mastery", "topic"),
    ("misconceptions", "topic"),
    ("chunks", "topic"),
    ("quiz_questions", "topic"),
    ("quiz_attempt_answers", "topic"),
    ("quiz_attempt_answers", "topic_key"),
    ("interaction_patterns", "topic"),
    ("topic_behavior", "topic"),
    ("recommendation_logs", "topic"),
    ("video_recommendation_cache", "topic"),
    ("reflections", "topic"),
    ("learning_resources", "topic"),
    ("misconception_rules", "topic"),
}

IGNORED_TOPIC_COLUMNS_ALLOWLIST: dict[tuple[str, str], str] = {
    ("learning_objectives", "topic_id"): "UUID FK to prerequisite_map.id which does not change on topic rename",
    ("learning_objectives", "subtopic_id"): "UUID FK to syllabus_subtopics.id",
    ("quiz_questions", "topic_id"): "UUID FK to prerequisite_map.id which does not change on topic rename",
    ("syllabus_subtopics", "topic_id"): "UUID FK to prerequisite_map.id which does not change on topic rename",
    ("question_curriculum_mappings", "topic_id"): "UUID FK to prerequisite_map.id which does not change on topic rename",
    ("question_curriculum_mappings", "subtopic_id"): "UUID FK to syllabus_subtopics.id",
    ("quiz_attempts", "topic_scores"): "JSON column handled via specialized JSON key rewrite in rename_topic",
    ("quiz_coverage_reports", "total_topics"): "Integer metric representing topic count, not a topic name",
    ("quiz_coverage_reports", "covered_topics"): "JSON/metric representation of coverage report",
    ("quiz_coverage_reports", "missing_topics"): "JSON/metric representation of coverage report",
    ("quiz_coverage_reports", "partially_covered_topics"): "JSON/metric representation of coverage report",
}


def merge_interaction_pattern_values(
    source_count: int,
    target_count: int,
    source_last: datetime | None,
    target_last: datetime | None,
) -> tuple[int, datetime | None]:
    """Pure arithmetic helper for merging InteractionPattern rows."""
    total_count = source_count + target_count
    valid_dates = [d for d in (source_last, target_last) if d is not None]
    latest_last = max(valid_dates) if valid_dates else None
    return total_count, latest_last


def merge_topic_behavior_values(b1: dict[str, Any], b2: dict[str, Any]) -> dict[str, Any]:
    """Pure arithmetic helper for merging TopicBehavior count dictionaries."""
    return {
        "message_count": int(b1.get("message_count", 0)) + int(b2.get("message_count", 0)),
        "follow_up_count": int(b1.get("follow_up_count", 0)) + int(b2.get("follow_up_count", 0)),
        "qt_conceptual": int(b1.get("qt_conceptual", 0)) + int(b2.get("qt_conceptual", 0)),
        "qt_example": int(b1.get("qt_example", 0)) + int(b2.get("qt_example", 0)),
        "qt_direct": int(b1.get("qt_direct", 0)) + int(b2.get("qt_direct", 0)),
    }


def derive_tag_from_counts(
    message_count: int,
    follow_up_count: int,
    qt_conceptual: int,
    qt_example: int,
    qt_direct: int,
) -> str | None:
    """Pure function deriving TopicBehavior learning_tag from counts."""
    total_qt = qt_conceptual + qt_example + qt_direct
    if total_qt < 3:
        return None
    if message_count >= 4 and (follow_up_count / max(message_count, 1)) >= 0.5:
        return "needs-repetition"
    if (qt_example / total_qt) >= 0.5:
        return "example-driven"
    if (qt_conceptual / total_qt) >= 0.6:
        return "concept-first"
    return None

_DRAFT_PROMPT = (
    "You are given the syllabus for a course. Extract the list of teachable topics, grouped "
    "roughly by module/unit order. For each topic give a one-sentence description and, where the "
    "syllabus makes it clear, which other topics in this same list it requires as prerequisites "
    "and which it is conceptually related to.\n\n"
    "Return ONLY a JSON array, no prose, no markdown. Each item:\n"
    '{{"topic": str, "description": str, "requires": [topic names], "related_concepts": [topic names]}}\n'
    "Every name in requires/related_concepts MUST be the exact 'topic' of another item.\n"
    "Aim for 8-30 topics. Keep names short (2-5 words).\n\n"
    "Syllabus:\n{syllabus}"
)


def _parse_json_array(raw: str) -> list[dict[str, Any]]:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"Could not parse topic JSON from LLM output: {raw[:200]!r}")


async def draft_from_syllabus(syllabus_text: str) -> list[dict[str, Any]]:
    from backend.llm.model_pool import model_pool
    from backend.services import rag_service

    provider, model_idx = model_pool.get_provider()
    prompt = _DRAFT_PROMPT.format(syllabus=syllabus_text[:12000])

    parsed: list[dict[str, Any]] | None = None
    raw = ""
    for attempt in range(2):
        raw = await provider.generate(prompt, max_tokens=2500)
        try:
            parsed = _parse_json_array(raw)
            break
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"[TOPIC DRAFT] attempt {attempt + 1} unparseable: {exc}")
            prompt += "\n\nRespond with ONLY the JSON array."

    if parsed is None:
        raise ValueError("LLM failed to produce a valid topic list.")

    model_pool.record_usage(model_idx, rag_service.estimate_tokens(prompt) + rag_service.estimate_tokens(raw))

    names = {str(item.get("topic", "")).strip() for item in parsed if item.get("topic")}
    cleaned: list[dict[str, Any]] = []
    for item in parsed:
        topic = str(item.get("topic", "")).strip()
        if not topic:
            continue
        cleaned.append(
            {
                "topic": topic[:500],
                "description": (str(item.get("description", "")).strip() or None),
                "requires": [r for r in map(str, item.get("requires", []) or []) if r in names and r != topic],
                "related_concepts": [
                    r for r in map(str, item.get("related_concepts", []) or []) if r in names and r != topic
                ],
            }
        )
    print(f"[TOPIC DRAFT] drafted {len(cleaned)} topics")
    return cleaned


def _validate_edges(topics: list[dict[str, Any]]) -> None:
    names = {t["topic"] for t in topics}
    for t in topics:
        for edge_field in ("requires", "related_concepts"):
            for ref in t.get(edge_field, []):
                if ref not in names:
                    raise ValueError(
                        f"Topic '{t['topic']}' {edge_field} references unknown topic '{ref}'."
                    )
            if t["topic"] in t.get(edge_field, []):
                raise ValueError(f"Topic '{t['topic']}' cannot reference itself in {edge_field}.")


def confirm(db: Session, subject_id: str, topics: list[dict[str, Any]], created_by: str) -> list[PrerequisiteMap]:
    subject = db.get(Subject, subject_id)
    if subject is None:
        raise ValueError(f"Subject '{subject_id}' not found.")

    seen: set[str] = set()
    for t in topics:
        name = t["topic"].strip()
        if not name:
            raise ValueError("Topic name cannot be empty.")
        if name.lower() in seen:
            raise ValueError(f"Duplicate topic '{name}'.")
        seen.add(name.lower())
    _validate_edges(topics)

    db.query(PrerequisiteMap).filter(PrerequisiteMap.subject_id == subject_id).delete()
    rows: list[PrerequisiteMap] = []
    for t in topics:
        row = PrerequisiteMap(
            subject_id=subject_id,
            subject=subject.name,
            topic=t["topic"].strip()[:500],
            description=(t.get("description") or None),
            requires=list(t.get("requires", [])),
            related_concepts=list(t.get("related_concepts", [])),
            created_by=created_by,
        )
        db.add(row)
        rows.append(row)
    db.commit()
    bump_anchor_version(subject_id)
    print(f"[TOPIC GRAPH] confirmed {len(rows)} topics for subject {subject_id}")
    return rows


def read_graph(db: Session, subject_id: str) -> list[dict[str, Any]]:
    rows = (
        db.query(PrerequisiteMap)
        .filter(PrerequisiteMap.subject_id == subject_id)
        .order_by(PrerequisiteMap.created_at, PrerequisiteMap.topic)
        .all()
    )
    return [
        {
            "id": str(r.id),
            "topic": r.topic,
            "description": r.description,
            "requires": list(r.requires or []),
            "related_concepts": list(r.related_concepts or []),
        }
        for r in rows
    ]


def get_syllabus_status(db: Session, subject_id: str) -> dict[str, Any]:
    subject = db.get(Subject, subject_id)
    if subject is None:
        raise ValueError(f"Subject '{subject_id}' not found.")

    rows = (
        db.query(PrerequisiteMap)
        .filter(PrerequisiteMap.subject_id == subject_id)
        .order_by(PrerequisiteMap.created_at, PrerequisiteMap.topic)
        .all()
    )

    if rows:
        topics = [
            {
                "id": str(r.id),
                "topic": r.topic,
                "description": r.description,
                "requires": list(r.requires or []),
                "related_concepts": list(r.related_concepts or []),
            }
            for r in rows
        ]
        latest_time = max(
            [r.updated_at or r.created_at for r in rows if r.updated_at or r.created_at] or [datetime.utcnow()]
        )
        return {
            "subject_id": str(subject.id),
            "subject_name": subject.name,
            "status": "approved",
            "topic_count": len(topics),
            "topics": topics,
            "updated_at": latest_time.isoformat() if latest_time else None,
        }

    return {
        "subject_id": str(subject.id),
        "subject_name": subject.name,
        "status": "missing",
        "topic_count": 0,
        "topics": [],
        "updated_at": None,
    }


def rename_topic(db: Session, subject_id: str, old_topic: str, new_topic: str) -> None:
    old_topic = old_topic.strip()
    new_topic = new_topic.strip()[:500]
    if not new_topic:
        raise ValueError("New topic name cannot be empty.")

    row = (
        db.query(PrerequisiteMap)
        .filter(PrerequisiteMap.subject_id == subject_id, PrerequisiteMap.topic == old_topic)
        .first()
    )
    if row is None:
        raise ValueError(f"Topic '{old_topic}' not found for this subject.")
    if old_topic == new_topic:
        return
    clash = (
        db.query(PrerequisiteMap)
        .filter(PrerequisiteMap.subject_id == subject_id, PrerequisiteMap.topic == new_topic)
        .first()
    )
    if clash is not None:
        raise ValueError(f"Topic '{new_topic}' already exists for this subject.")

    savepoint = db.begin_nested()
    try:
        row.topic = new_topic
        row.updated_at = datetime.now(timezone.utc)

        for edge_row in db.query(PrerequisiteMap).filter(PrerequisiteMap.subject_id == subject_id).all():
            if edge_row.requires and old_topic in edge_row.requires:
                edge_row.requires = [new_topic if x == old_topic else x for x in edge_row.requires]
            if edge_row.related_concepts and old_topic in edge_row.related_concepts:
                edge_row.related_concepts = [
                    new_topic if x == old_topic else x for x in edge_row.related_concepts
                ]

        # Simple cascades: Chunk, MisconceptionRule
        db.query(Chunk).filter(
            Chunk.subject_id == subject_id, Chunk.topic == old_topic
        ).update({Chunk.topic: new_topic}, synchronize_session=False)

        db.query(MisconceptionRule).filter(
            MisconceptionRule.subject_id == subject_id, MisconceptionRule.topic == old_topic
        ).update({MisconceptionRule.topic: new_topic}, synchronize_session=False)

        # VideoRecommendationCache (merge-aware)
        old_cache_rows = (
            db.query(VideoRecommendationCache)
            .filter(
                VideoRecommendationCache.subject_id == subject_id,
                VideoRecommendationCache.topic == old_topic,
            )
            .all()
        )
        for cache_row in old_cache_rows:
            target_cache = (
                db.query(VideoRecommendationCache)
                .filter(
                    VideoRecommendationCache.subject_id == subject_id,
                    VideoRecommendationCache.topic == new_topic,
                )
                .first()
            )
            if target_cache is not None:
                db.delete(cache_row)
            else:
                cache_row.topic = new_topic
                cache_row.fetched_at = datetime.now(timezone.utc)

        # TopicBehavior (merge-aware, subject_id matches or is None)
        old_behaviors = (
            db.query(TopicBehavior)
            .filter(
                or_(TopicBehavior.subject_id == subject_id, TopicBehavior.subject_id.is_(None)),
                TopicBehavior.topic == old_topic,
            )
            .all()
        )
        for old_tb in old_behaviors:
            if old_tb.subject_id is None:
                target_tb = (
                    db.query(TopicBehavior)
                    .filter(
                        TopicBehavior.student_id == old_tb.student_id,
                        TopicBehavior.subject_id.is_(None),
                        TopicBehavior.topic == new_topic,
                    )
                    .first()
                )
            else:
                target_tb = (
                    db.query(TopicBehavior)
                    .filter(
                        TopicBehavior.student_id == old_tb.student_id,
                        TopicBehavior.subject_id == old_tb.subject_id,
                        TopicBehavior.topic == new_topic,
                    )
                    .first()
                )

            if target_tb is not None:
                merged = merge_topic_behavior_values(
                    {
                        "message_count": old_tb.message_count,
                        "follow_up_count": old_tb.follow_up_count,
                        "qt_conceptual": old_tb.qt_conceptual,
                        "qt_example": old_tb.qt_example,
                        "qt_direct": old_tb.qt_direct,
                    },
                    {
                        "message_count": target_tb.message_count,
                        "follow_up_count": target_tb.follow_up_count,
                        "qt_conceptual": target_tb.qt_conceptual,
                        "qt_example": target_tb.qt_example,
                        "qt_direct": target_tb.qt_direct,
                    },
                )
                target_tb.message_count = merged["message_count"]
                target_tb.follow_up_count = merged["follow_up_count"]
                target_tb.qt_conceptual = merged["qt_conceptual"]
                target_tb.qt_example = merged["qt_example"]
                target_tb.qt_direct = merged["qt_direct"]
                target_tb.learning_tag = derive_tag_from_counts(
                    message_count=merged["message_count"],
                    follow_up_count=merged["follow_up_count"],
                    qt_conceptual=merged["qt_conceptual"],
                    qt_example=merged["qt_example"],
                    qt_direct=merged["qt_direct"],
                )
                valid_dates = [d for d in (old_tb.updated_at, target_tb.updated_at) if d is not None]
                target_tb.updated_at = max(valid_dates) if valid_dates else datetime.now(timezone.utc)
                db.delete(old_tb)
            else:
                old_tb.topic = new_topic
                old_tb.updated_at = datetime.now(timezone.utc)

        subject_class_ids = _subject_class_ids(db, subject_id)
        if subject_class_ids:
            quiz_ids = [
                row[0]
                for row in db.query(Quiz.id).filter(Quiz.class_id.in_(subject_class_ids)).all()
            ]
            if quiz_ids:
                db.query(QuizQuestion).filter(
                    QuizQuestion.quiz_id.in_(quiz_ids), QuizQuestion.topic == old_topic
                ).update({QuizQuestion.topic: new_topic}, synchronize_session=False)

            old_key = normalize_topic_key(old_topic)
            new_key = normalize_topic_key(new_topic)

            # Update QuizAttemptAnswer topic and topic_key
            db.query(QuizAttemptAnswer).filter(
                QuizAttemptAnswer.class_id.in_(subject_class_ids),
                or_(QuizAttemptAnswer.topic_key == old_key, QuizAttemptAnswer.topic == old_topic),
            ).update(
                {QuizAttemptAnswer.topic: new_topic, QuizAttemptAnswer.topic_key: new_key},
                synchronize_session=False,
            )

            # Rewrite QuizAttempt.topic_scores JSON
            if quiz_ids:
                attempts = (
                    db.query(QuizAttempt)
                    .filter(QuizAttempt.quiz_id.in_(quiz_ids))
                    .all()
                )
                for att in attempts:
                    if att.topic_scores:
                        try:
                            scores = json.loads(att.topic_scores)
                            if isinstance(scores, dict) and old_topic in scores:
                                scores[new_topic] = scores.pop(old_topic)
                                att.topic_scores = json.dumps(scores)
                        except Exception:
                            pass

        # Update Misconception, RecommendationLog, Reflection, LearningResource
        db.query(Misconception).filter(
            Misconception.class_id.in_(subject_class_ids), Misconception.topic == old_topic
        ).update({Misconception.topic: new_topic}, synchronize_session=False)

        db.query(RecommendationLog).filter(
            RecommendationLog.class_id.in_(subject_class_ids), RecommendationLog.topic == old_topic
        ).update({RecommendationLog.topic: new_topic}, synchronize_session=False)

        db.query(Reflection).filter(
            Reflection.class_id.in_(subject_class_ids), Reflection.topic == old_topic
        ).update({Reflection.topic: new_topic}, synchronize_session=False)

        db.query(LearningResource).filter(
            LearningResource.class_id.in_(subject_class_ids), LearningResource.topic == old_topic
        ).update({LearningResource.topic: new_topic}, synchronize_session=False)

        # InteractionPattern (merge-aware)
        old_patterns = (
            db.query(InteractionPattern)
            .filter(
                InteractionPattern.class_id.in_(subject_class_ids),
                InteractionPattern.topic == old_topic,
            )
            .all()
        )
        for p in old_patterns:
            target_p = (
                db.query(InteractionPattern)
                .filter(
                    InteractionPattern.student_id == p.student_id,
                    InteractionPattern.class_id == p.class_id,
                    InteractionPattern.topic == new_topic,
                )
                .first()
            )
            if target_p is not None:
                tot_q, last_dt = merge_interaction_pattern_values(
                    p.questions_asked, target_p.questions_asked, p.last_asked_at, target_p.last_asked_at
                )
                target_p.questions_asked = tot_q
                target_p.last_asked_at = last_dt
                db.delete(p)
            else:
                p.topic = new_topic

        # TopicMastery: in-place rename if no target row; merge if target row exists
        old_masteries = (
            db.query(TopicMastery)
            .filter(
                TopicMastery.class_id.in_(subject_class_ids),
                TopicMastery.topic == old_topic,
            )
            .all()
        )
        for old_m in old_masteries:
            target_m = (
                db.query(TopicMastery)
                .filter(
                    TopicMastery.student_id == old_m.student_id,
                    TopicMastery.class_id == old_m.class_id,
                    TopicMastery.topic == new_topic,
                )
                .first()
            )
            if target_m is None:
                # In-place rename preserves row ID, last_attempt_at, trend, mastery_v2
                old_m.topic = new_topic
                old_m.updated_at = datetime.now(timezone.utc)
            else:
                # Target row exists: merge old_m into target_m
                target_m.attempt_count = (target_m.attempt_count or 0) + (old_m.attempt_count or 0)
                valid_attempts = [d for d in (old_m.last_attempt_at, target_m.last_attempt_at) if d is not None]
                if valid_attempts:
                    target_m.last_attempt_at = max(valid_attempts)

                scores = _topic_score_history(db, str(target_m.student_id), str(target_m.class_id), new_topic)
                if scores:
                    target_m.mastery_score = calculate_mastery(scores)
                    target_m.trend = calculate_trend(scores)
                else:
                    # Weighted average if no individual attempt answer scores are available
                    c_old = old_m.attempt_count or 1
                    c_tgt = target_m.attempt_count or 1
                    target_m.mastery_score = round(
                        ((old_m.mastery_score or 0.0) * c_old + (target_m.mastery_score or 0.0) * c_tgt) / (c_old + c_tgt),
                        4,
                    )

                # Merge mastery_v2 if present: prefer sufficient evidence
                if old_m.mastery_v2 and not target_m.mastery_v2:
                    target_m.mastery_v2 = old_m.mastery_v2
                elif old_m.mastery_v2 and target_m.mastery_v2:
                    try:
                        v2_old = json.loads(old_m.mastery_v2) if isinstance(old_m.mastery_v2, str) else old_m.mastery_v2
                        v2_tgt = json.loads(target_m.mastery_v2) if isinstance(target_m.mastery_v2, str) else target_m.mastery_v2
                        if v2_old.get("evidence_state") == "sufficient" and v2_tgt.get("evidence_state") != "sufficient":
                            target_m.mastery_v2 = old_m.mastery_v2
                    except Exception:
                        pass

                target_m.updated_at = datetime.now(timezone.utc)
                db.delete(old_m)

        savepoint.commit()
        db.flush()
        bump_anchor_version(subject_id)
        print(f"[TOPIC GRAPH] renamed '{old_topic}' -> '{new_topic}' for subject {subject_id}")
    except Exception:
        savepoint.rollback()
        raise


def _subject_class_ids(db: Session, subject_id: str) -> list[Any]:
    from backend.models.db import Class

    return [row[0] for row in db.query(Class.id).filter(Class.subject_id == subject_id).all()]


_anchor_cache: dict[str, tuple[int, list[str], list[list[float]]]] = {}
_anchor_version: dict[str, int] = {}


def bump_anchor_version(subject_id: str) -> None:
    _anchor_version[subject_id] = _anchor_version.get(subject_id, 0) + 1


def topic_anchors(db: Session, subject_id: str, embedding_model: Any) -> tuple[list[str], list[list[float]]]:
    version = _anchor_version.get(subject_id, 0)
    cached = _anchor_cache.get(subject_id)
    if cached is not None and cached[0] == version:
        return cached[1], cached[2]

    from backend.pipeline.embedder import embed_texts

    rows = db.query(PrerequisiteMap).filter(PrerequisiteMap.subject_id == subject_id).all()
    names = [r.topic for r in rows]
    if not names:
        _anchor_cache[subject_id] = (version, [], [])
        return [], []

    anchor_texts = [
        f"{r.topic}. {r.description}" if r.description else r.topic for r in rows
    ]
    vectors = embed_texts(anchor_texts, model=embedding_model)
    _anchor_cache[subject_id] = (version, names, vectors)
    print(f"[TOPIC GRAPH] embedded {len(names)} topic anchors for subject {subject_id}")
    return names, vectors
