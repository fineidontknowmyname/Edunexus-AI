import json
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models.db import Chunk, Document, MasteryTrend, Subject, TopicMastery, VideoRecommendationCache
from backend.services import behavior_service, routing_service, topic_graph_service

VIDEO_CACHE_TTL_DAYS = 30
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


def _fetch_youtube_videos(subject_name: str, topic: str) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.youtube_api_key:
        print("[RECOMMENDATION] No YOUTUBE_API_KEY configured — skipping video recommendations")
        return []
    try:
        response = httpx.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "q": f"{subject_name} {topic}",
                "type": "video",
                "maxResults": 3,
                "safeSearch": "strict",
                "key": settings.youtube_api_key,
            },
            timeout=5.0,
        )
        response.raise_for_status()
        items = response.json().get("items", [])
    except httpx.HTTPError as e:
        print(f"[RECOMMENDATION WARNING] YouTube API call failed: {e}")
        return []

    return [
        {
            "video_id": item["id"]["videoId"],
            "title": item["snippet"]["title"],
            "channel": item["snippet"]["channelTitle"],
            "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}",
        }
        for item in items
        if item.get("id", {}).get("videoId")
    ]


def _get_cached_videos(db: Session, subject_id: str, subject_name: str, topic: str) -> list[dict[str, Any]]:
    cutoff = datetime.utcnow() - timedelta(days=VIDEO_CACHE_TTL_DAYS)
    row = (
        db.query(VideoRecommendationCache)
        .filter(VideoRecommendationCache.subject_id == subject_id, VideoRecommendationCache.topic == topic)
        .first()
    )
    if row and row.fetched_at >= cutoff:
        return json.loads(row.videos_json)

    videos = _fetch_youtube_videos(subject_name, topic)
    if row is None:
        db.add(VideoRecommendationCache(subject_id=subject_id, topic=topic, videos_json=json.dumps(videos)))
    else:
        row.videos_json = json.dumps(videos)
        row.fetched_at = datetime.utcnow()
    db.commit()
    return videos


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
    stalled = (
        mastery is not None
        and mastery.attempt_count >= STALLED_MIN_ATTEMPTS
        and mastery.mastery_score < STALLED_MASTERY_CEILING
        and mastery.trend in (MasteryTrend.stable, MasteryTrend.declining)
    )

    reason = None
    if routing == routing_service.INTERVENE:
        reason = "There's an open misconception on this topic. A guided session will unlock it for quizzes again."
    elif learning_tag in GUIDED_LEARNING_TAGS:
        reason = "You've been coming back to this topic, so a step-by-step guided session should help."
    elif stalled:
        reason = "Your scores on this topic haven't moved after a few attempts, so let's work through it together."

    if reason is not None:
        return {
            "routing": routing,
            "learning_tag": learning_tag,
            "mode": "ai_session",
            "reason": reason,
            "sections": [],
            "videos": [],
            "socratic_seed_message": topic,
        }

    sections: list[dict[str, Any]] = []
    videos: list[dict[str, Any]] = []
    if subject_id:
        subject = db.get(Subject, subject_id)
        sections = _curriculum_sections(db, class_id, subject_id, topic, embedding_model)
        videos = _get_cached_videos(db, subject_id, subject.name if subject else topic, topic)

    return {
        "routing": routing,
        "learning_tag": learning_tag,
        "mode": "static",
        "reason": None,
        "sections": sections,
        "videos": videos,
        "socratic_seed_message": None,
    }
