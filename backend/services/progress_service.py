import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.core.prerequisites import load_prerequisite_map, load_topic_graph_db, topic_names_db
from backend.core.time_utils import local_today
from backend.core.tracking_constants import (
    MASTERED_THRESHOLD,
    TOPIC_REVIEW_DUE_DAYS,
    URGENT_THRESHOLD,
    WEAK_THRESHOLD,
)
from backend.models.db import Class, Engagement, InteractionPattern, MasteryTrend, Quiz, QuizAttempt, TopicMastery, User
from backend.services import context_service, evidence_service
from backend.services.mastery_v2 import normalize_topic_key

STALE_AFTER_DAYS = TOPIC_REVIEW_DUE_DAYS


def calculate_mastery(scores_most_recent_first: list[float]) -> float:
    n = len(scores_most_recent_first)
    if n == 0:
        return 0.0
    if n == 1:
        return scores_most_recent_first[0]
    if n == 2:
        return scores_most_recent_first[0] * 0.6 + scores_most_recent_first[1] * 0.4

    recent = scores_most_recent_first[0] * 0.5 + scores_most_recent_first[1] * 0.3
    older = scores_most_recent_first[2:]
    return recent + (sum(older) / len(older)) * 0.2


TREND_THRESHOLD = 0.1


def calculate_trend(scores_most_recent_first: list[float]) -> MasteryTrend:
    if len(scores_most_recent_first) < 3:
        return MasteryTrend.not_started if not scores_most_recent_first else MasteryTrend.stable
    newest, middle, oldest = scores_most_recent_first[:3]
    delta = newest - (middle + oldest) / 2
    if delta >= TREND_THRESHOLD:
        return MasteryTrend.improving
    if delta <= -TREND_THRESHOLD:
        return MasteryTrend.declining
    return MasteryTrend.stable


def _topic_score_history(db: Session, student_id: str, class_id: str, topic: str) -> list[float]:
    attempts = (
        db.query(QuizAttempt)
        .join(Quiz, QuizAttempt.quiz_id == Quiz.id)
        .filter(
            QuizAttempt.student_id == student_id,
            Quiz.class_id == class_id,
            QuizAttempt.completed == True,  # noqa: E712
        )
        .order_by(QuizAttempt.completed_at.desc())
        .all()
    )
    target_key = normalize_topic_key(topic)
    scores: list[float] = []
    for attempt in attempts:
        if not attempt.topic_scores:
            continue
        try:
            topic_scores: dict[str, float] = json.loads(attempt.topic_scores)
        except json.JSONDecodeError:
            continue
        matched_val = None
        for k, v in topic_scores.items():
            if normalize_topic_key(k) == target_key:
                matched_val = v
        if matched_val is not None:
            try:
                scores.append(float(matched_val))
            except (TypeError, ValueError):
                pass
    return scores


def update_mastery_after_attempt(
    db: Session,
    student_id: str,
    class_id: str,
    topic_scores: dict[str, float],
    topic_passed: dict[str, bool] | None = None,
) -> dict[str, Any]:
    topic_passed = topic_passed or {}
    updated_topics = {}
    class_row = db.get(Class, class_id)
    subject_id = class_row.subject_id if class_row else None
    for topic in topic_scores:
        if not topic or topic.strip().lower() in ("general", "unmapped", "none"):
            continue
        history = _topic_score_history(db, student_id, class_id, topic)
        mastery_score = calculate_mastery(history)
        trend = calculate_trend(history)
        attempt_count = len(history)

        row = (
            db.query(TopicMastery)
            .filter(TopicMastery.student_id == student_id, TopicMastery.class_id == class_id, TopicMastery.topic == topic)
            .first()
        )
        if row is None:
            row = TopicMastery(student_id=student_id, class_id=class_id, subject_id=subject_id, topic=topic)
            db.add(row)
        elif row.subject_id is None:
            row.subject_id = subject_id

        row.mastery_score = mastery_score
        row.attempt_count = attempt_count
        row.trend = trend
        row.last_attempt_at = datetime.now(timezone.utc)
        if topic in topic_passed:
            row.last_quiz_passed = topic_passed[topic]

        updated_topics[topic] = {
            "mastery_score": mastery_score,
            "trend": trend.value,
            "attempt_count": attempt_count,
            "last_quiz_passed": row.last_quiz_passed,
        }
        print(f"[PROGRESS] Mastery updated: student={student_id} topic={topic} score={mastery_score:.3f} trend={trend.value} attempts={attempt_count}")

    db.flush()
    return updated_topics


def _first_answers_only(rows: list[Any]) -> list[Any]:
    if not rows:
        return []

    def _sort_key(r: Any) -> tuple[bool, Any]:
        val = r.get("answered_at") if isinstance(r, dict) else getattr(r, "answered_at", None)
        return (val is None, val)

    sorted_asc = sorted(rows, key=_sort_key)
    seen_qids: set[Any] = set()
    result: list[Any] = []

    for r in sorted_asc:
        qid = r.get("question_id") if isinstance(r, dict) else getattr(r, "question_id", None)
        if qid is None:
            result.append(r)
        elif qid not in seen_qids:
            seen_qids.add(qid)
            result.append(r)

    return result


def update_mastery_v2_after_attempt(
    db: Session,
    student_id: str,
    topics: list[str] | dict[str, Any] | set[str],
    class_id: str | None = None,
) -> dict[str, Any]:
    from backend.core.config import get_settings
    from backend.models.db import QuizAttemptAnswer
    from backend.services.mastery_v2 import AttemptEvidence, compute_mastery, normalize_topic_key, result_to_dict

    settings = get_settings()
    if not settings.mastery_v2_enabled:
        return {}

    v2_results: dict[str, Any] = {}
    topic_list = list(topics.keys()) if isinstance(topics, dict) else list(topics)
    for topic in topic_list:
        topic_key = normalize_topic_key(topic)
        if not topic_key:
            continue

        q = (
            db.query(
                QuizAttemptAnswer.question_id,
                QuizAttemptAnswer.attempt_id,
                QuizAttemptAnswer.is_correct,
                QuizAttemptAnswer.answered_at,
                QuizAttemptAnswer.option_count,
            )
            .filter(
                QuizAttemptAnswer.student_id == student_id,
                QuizAttemptAnswer.topic_key == topic_key,
            )
        )
        if class_id is not None:
            q = q.filter(QuizAttemptAnswer.class_id == class_id)

        rows = (
            q.order_by(QuizAttemptAnswer.answered_at.desc())
            .limit(50)
            .all()
        )
        first_rows = _first_answers_only(rows)

        attempts = [
            AttemptEvidence(
                question_id=str(r.question_id),
                session_id=str(r.attempt_id),
                correct=r.is_correct,
                timestamp=r.answered_at,
                option_count=r.option_count,
                difficulty=None,
            )
            for r in first_rows
        ]

        mastery_res = compute_mastery(attempts)
        dict_res = result_to_dict(mastery_res)
        v2_results[topic] = dict_res

        tm_query = (
            db.query(TopicMastery)
            .filter(
                TopicMastery.student_id == student_id,
                TopicMastery.topic == topic,
            )
        )
        if class_id is not None:
            tm_query = tm_query.filter(TopicMastery.class_id == class_id)

        tm_rows = tm_query.all()
        for tm_row in tm_rows:
            tm_row.mastery_v2 = json.dumps(dict_res)

    db.flush()
    return v2_results


def _assign_priority(attempted: bool, score: float, in_scope: bool, days_remaining: int | None) -> int:
    if attempted and score < URGENT_THRESHOLD:
        return 0
    if not attempted and in_scope and days_remaining is not None and days_remaining <= 7:
        return 1
    if attempted and URGENT_THRESHOLD <= score < WEAK_THRESHOLD:
        return 2
    if not attempted:
        return 3
    if WEAK_THRESHOLD <= score < MASTERED_THRESHOLD:
        return 4
    return 5


def get_syllabus_topics_for_class(db: Session, class_id: str) -> list[str]:
    class_row = db.get(Class, class_id)
    if class_row and class_row.subject_id:
        db_topics = topic_names_db(db, str(class_row.subject_id))
        if db_topics:
            return db_topics
    if class_row and class_row.subject:
        legacy_map = load_prerequisite_map(class_row.subject)
        if legacy_map:
            return list(legacy_map.keys())
    return []


def compute_dashboard_summary(
    mastery: dict[str, Any] | list[float],
    syllabus_topics: list[str] | int = 0,
) -> dict[str, Any]:
    if isinstance(syllabus_topics, int):
        total_syllabus_topics = syllabus_topics
    else:
        total_syllabus_topics = len(syllabus_topics)

    if isinstance(mastery, list):
        assessed_scores = [float(s) for s in mastery]
        attempted_topics = len(assessed_scores)
    else:
        assessed_entries = [v for v in mastery.values() if v.get("attempts", 0) > 0]
        assessed_scores = [v["score"] for v in assessed_entries]
        attempted_topics = len(assessed_entries)

    assessed_average = (
        round(sum(assessed_scores) / len(assessed_scores), 4)
        if assessed_scores
        else None
    )
    mastered_topics = sum(1 for s in assessed_scores if s >= MASTERED_THRESHOLD)
    coverage_ratio = (
        round(attempted_topics / total_syllabus_topics, 4)
        if total_syllabus_topics > 0
        else 0.0
    )
    return {
        "assessed_average": assessed_average,
        "attempted_topics": attempted_topics,
        "mastered_topics": mastered_topics,
        "total_syllabus_topics": total_syllabus_topics,
        "coverage_ratio": coverage_ratio,
    }


def get_learning_path(db: Session, student_id: str, class_id: str) -> dict[str, Any]:
    student_context = context_service.assemble_student_context(db, student_id, class_id)
    class_context = context_service.assemble_class_context(db, class_id)

    subject_id = class_context.get("subject_id")
    topic_graph = load_topic_graph_db(db, subject_id) if subject_id else {}
    if topic_graph:
        vocabulary = list(topic_graph.keys())
    else:
        vocabulary = list(load_prerequisite_map(class_context["subject"]).keys())

    uploaded_topics = set(context_service.get_uploaded_topics(db, class_id, class_context["subject"]))
    mastery = student_context["mastery"]
    already_tracked = set(mastery.keys())
    syllabus_topics = [t for t in vocabulary if t in uploaded_topics or t in already_tracked or not uploaded_topics]
    upcoming = student_context.get("upcoming_focus")
    topics_in_scope = set(upcoming["topics_in_scope"]) if upcoming else set()
    days_remaining = upcoming["days_remaining"] if upcoming else None

    entries = []
    for index, topic in enumerate(syllabus_topics):
        entry = mastery.get(topic)
        attempted = bool(entry and entry["attempts"] > 0)
        score = entry["score"] if entry else 0.0
        in_scope = topic in topics_in_scope
        priority = _assign_priority(attempted, score, in_scope, days_remaining)

        entries.append({
            "topic": topic,
            "priority": priority,
            "mastery_score": score,
            "attempts": entry["attempts"] if entry else 0,
            "trend": entry["trend"] if entry else "not_started",
            "in_assessment_scope": in_scope,
            "syllabus_index": index,
        })

    entries.sort(key=lambda e: (e["priority"], 0 if e["in_assessment_scope"] else 1, e["syllabus_index"]))

    cold_start = len(mastery) == 0
    print(f"[PROGRESS] Learning path built: {len(entries)} topics, cold_start={cold_start}")

    return {"cold_start": cold_start, "path": entries}


def get_dashboard(db: Session, student_id: str, class_id: str) -> dict[str, Any]:
    student_context = context_service.assemble_student_context(db, student_id, class_id)
    mastery = student_context["mastery"]

    user = db.get(User, student_id)
    user_tz = getattr(user, "timezone", "UTC") if user else "UTC"
    today = local_today(user_tz)

    engagement_row = (
        db.query(Engagement)
        .filter(Engagement.student_id == student_id, Engagement.class_id == class_id)
        .first()
    )
    engagement = evidence_service.build_engagement_payload(engagement_row, today)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale_cutoff = now - timedelta(days=STALE_AFTER_DAYS)
    interaction_rows = db.query(InteractionPattern).filter(
        InteractionPattern.student_id == student_id, evidence_service.interaction_scope(class_id)
    ).all()
    last_touched: dict[str, datetime] = {}
    for row in interaction_rows:
        if row.last_asked_at:
            last_touched[row.topic] = row.last_asked_at

    mastery_rows = db.query(TopicMastery).filter(
        TopicMastery.student_id == student_id, TopicMastery.class_id == class_id
    ).all()
    for row in mastery_rows:
        if row.last_attempt_at and (row.topic not in last_touched or row.last_attempt_at > last_touched[row.topic]):
            last_touched[row.topic] = row.last_attempt_at

    stale_topics = [topic for topic, last in last_touched.items() if last < stale_cutoff]

    print(f"[PROGRESS] Dashboard built for student={student_id}: {len(mastery)} topics tracked, {len(stale_topics)} stale")

    v2_by_topic: dict[str, Any] = {}
    try:
        from backend.core.config import get_settings
        if get_settings().mastery_v2_enabled:
            from backend.models.schemas import _parse_mastery_v2
            from backend.services.mastery_v2 import apply_staleness
            for row in mastery_rows:
                raw_v2 = getattr(row, "mastery_v2", None)
                if raw_v2:
                    parsed_v2 = _parse_mastery_v2(raw_v2)
                    v2_by_topic[row.topic] = apply_staleness(parsed_v2)
    except Exception as exc:
        print(f"[PROGRESS WARNING] Failed to parse mastery_v2 for dashboard: {exc}")

    syllabus_topics = get_syllabus_topics_for_class(db, class_id)
    summary = compute_dashboard_summary(mastery, syllabus_topics)

    return {
        "mastery": [
            {
                "topic": topic,
                "score": v["score"],
                "trend": v["trend"],
                "attempts": v["attempts"],
                "mastery_v2": v2_by_topic.get(topic),
            }
            for topic, v in mastery.items()
        ],
        "engagement": engagement,
        "upcoming_focus": student_context.get("upcoming_focus"),
        "stale_topics": stale_topics,
        "summary": summary,
    }
