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
        tier = ContextTier.strong.value
    elif weak_count <= 2 and not has_misconceptions:
        tier = ContextTier.moderate_weak.value
    else:
        tier = ContextTier.significant_gaps.value

    print(f"[CACHE] Context tier computed: {tier} (weak_count={weak_count}, misconceptions={has_misconceptions})")
    return tier


def check_cache(
    db: Session,
    query_vector: list[float],
    subject: str | None,
    context_tier: str,
    subject_id: str | None = None,
    learning_tag: str | None = None,
) -> ResponseCache | None:
    cutoff = datetime.utcnow() - timedelta(hours=TTL_HOURS)
    distance_expr = ResponseCache.query_embedding.cosine_distance(query_vector)

    scope_filter = (
        ResponseCache.subject_id == subject_id if subject_id else ResponseCache.subject == subject
    )
    row = (
        db.query(ResponseCache, distance_expr.label("distance"))
        .filter(
            scope_filter,
            ResponseCache.context_tier == ContextTier(context_tier),
            ResponseCache.learning_tag.is_(learning_tag) if learning_tag is None
            else ResponseCache.learning_tag == learning_tag,
            ResponseCache.created_at >= cutoff,
        )
        .order_by(distance_expr)
        .first()
    )
    if row is None:
        print(f"[CACHE MISS] No candidate rows for subject={subject} tier={context_tier}")
        return None

    candidate, distance = row
    similarity = 1 - distance
    if similarity < SIMILARITY_THRESHOLD:
        print(f"[CACHE MISS] Closest candidate similarity={similarity:.3f} < threshold={SIMILARITY_THRESHOLD}")
        return None

    print(f"[CACHE HIT] similarity={similarity:.3f} cache_id={candidate.id} — 0 tokens spent")
    return candidate


def store_cache(
    db: Session,
    query_vector: list[float],
    subject: str | None,
    context_tier: str,
    response_text: str,
    chunk_ids_used: list[UUID],
    source_type: str,
    subject_id: str | None = None,
    learning_tag: str | None = None,
) -> None:
    entry = ResponseCache(
        query_embedding=query_vector,
        subject=subject,
        subject_id=subject_id,
        context_tier=ContextTier(context_tier),
        learning_tag=learning_tag,
        response_text=response_text,
        chunk_ids_used=chunk_ids_used or None,
        source_type=SourceType(source_type),
    )
    db.add(entry)
    db.commit()
    print(f"[CACHE] Stored entry id={entry.id} subject={subject}/{subject_id} tier={context_tier} tag={learning_tag}")
