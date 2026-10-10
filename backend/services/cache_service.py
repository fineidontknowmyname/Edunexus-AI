from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from backend.models.db import ContextTier, ResponseCache, SourceType

SIMILARITY_THRESHOLD = 0.92
TTL_HOURS = 24


def compute_context_tier(student_context: dict[str, Any]) -> str:
    weak_count = len(student_context["weak_topics"])
    has_misconceptions = len(student_context["misconceptions"]) > 0

    if weak_count == 0 and not has_misconceptions:
        return ContextTier.strong.value
    if weak_count <= 2 and not has_misconceptions:
        return ContextTier.moderate_weak.value
    return ContextTier.significant_gaps.value


def _nullable_eq(column, value):
    return column.is_(None) if value is None else column == value


def check_cache(
    db: Session,
    query_vector: list[float],
    class_id: str,
    subject_id: str | None,
    context_tier: str,
    learning_tag: str | None,
    session_mode: str,
) -> ResponseCache | None:
    cutoff = datetime.utcnow() - timedelta(hours=TTL_HOURS)
    distance_expr = ResponseCache.query_embedding.cosine_distance(query_vector)
    row = (
        db.query(ResponseCache, distance_expr.label("distance"))
        .filter(
            ResponseCache.class_id == class_id,
            _nullable_eq(ResponseCache.subject_id, subject_id),
            ResponseCache.context_tier == ContextTier(context_tier),
            _nullable_eq(ResponseCache.learning_tag, learning_tag),
            ResponseCache.session_mode == session_mode,
            ResponseCache.created_at >= cutoff,
        )
        .order_by(distance_expr)
        .first()
    )
    if row is None:
        return None
    candidate, distance = row
    if 1 - distance < SIMILARITY_THRESHOLD:
        return None
    print(f"[CACHE HIT] similarity={1 - distance:.3f} cache_id={candidate.id}")
    return candidate


def store_cache(
    db: Session,
    query_vector: list[float],
    class_id: str,
    subject: str | None,
    subject_id: str | None,
    context_tier: str,
    learning_tag: str | None,
    session_mode: str,
    response_text: str,
    chunk_ids_used: list[UUID],
    source_type: str,
) -> None:
    db.add(
        ResponseCache(
            query_embedding=query_vector,
            class_id=class_id,
            subject=subject,
            subject_id=subject_id,
            context_tier=ContextTier(context_tier),
            learning_tag=learning_tag,
            session_mode=session_mode,
            response_text=response_text,
            chunk_ids_used=chunk_ids_used or None,
            source_type=SourceType(source_type),
        )
    )
    db.commit()
