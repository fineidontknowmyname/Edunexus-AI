"""Centralized thresholds and tracking constants for EduNexus student tracking."""

from typing import Literal

MASTERED_THRESHOLD: float = 0.70
WEAK_THRESHOLD: float = 0.60
URGENT_THRESHOLD: float = 0.40
ENGAGEMENT_INACTIVE_DAYS: int = 5
TOPIC_REVIEW_DUE_DAYS: int = 7
DUPLICATE_SUBMISSION_WINDOW_SECONDS: int = 30

TopicCategory = Literal["insufficient", "weak", "developing", "strong"]


def classify_topic(
    attempt_count: int,
    evidence_state: str | None,
    band: str | None,
    score: float,
) -> TopicCategory:
    """Pure classifier returning exactly one of: insufficient | weak | developing | strong.

    Rules:
    - insufficient if attempt_count == 0 or evidence_state in (None, '', 'none', 'insufficient').
    - otherwise if V2 band is present (not None/empty/unknown):
        low -> weak
        medium -> developing
        high -> strong
    - otherwise use V1 score against WEAK_THRESHOLD (0.60) and MASTERED_THRESHOLD (0.70).
    """
    if attempt_count == 0 or not evidence_state or evidence_state in ("none", "insufficient"):
        return "insufficient"

    clean_band = (band or "").strip().lower()
    if clean_band in ("low", "medium", "high"):
        if clean_band == "low":
            return "weak"
        if clean_band == "medium":
            return "developing"
        return "strong"

    # Fallback to V1 score
    try:
        s = float(score)
    except (TypeError, ValueError):
        s = 0.0

    if s < WEAK_THRESHOLD:
        return "weak"
    if s < MASTERED_THRESHOLD:
        return "developing"
    return "strong"

