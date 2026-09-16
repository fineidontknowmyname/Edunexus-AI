import json
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models.db import Chunk, Subject, VideoRecommendationCache
from backend.services import behavior_service, routing_service, topic_graph_service

VIDEO_CACHE_TTL_DAYS = 30
GUIDED_LEARNING_TAGS = {"needs-repetition"}


def _curriculum_sections(
    db: Session, subject_id: str, topic: str, embedding_model: Any, top_k: int = 5
) -> list[dict[str, Any]]:
    names, vectors = topic_graph_service.topic_anchors(db, subject_id, embedding_model)
    if topic not in names:
        return []
    anchor_vector = vectors[names.index(topic)]

    distance_expr = Chunk.embedding.cosine_distance(anchor_vector)
    rows = (
        db.query(Chunk, distance_expr.label("distance"))
        .filter(Chunk.subject_id == subject_id, Chunk.topic == topic)
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

    if learning_tag in GUIDED_LEARNING_TAGS:
        print(f"[RECOMMENDATION] student={student_id} topic={topic!r} tag={learning_tag!r} -> ai_session")
        return {
            "routing": routing,
            "learning_tag": learning_tag,
            "mode": "ai_session",
            "sections": [],
            "videos": [],
            "socratic_seed_message": topic,
        }

    sections: list[dict[str, Any]] = []
    videos: list[dict[str, Any]] = []
    if subject_id:
        subject = db.get(Subject, subject_id)
        sections = _curriculum_sections(db, subject_id, topic, embedding_model)
        videos = _get_cached_videos(db, subject_id, subject.name if subject else topic, topic)

    print(
        f"[RECOMMENDATION] student={student_id} topic={topic!r} tag={learning_tag!r} -> "
        f"static ({len(sections)} sections, {len(videos)} videos)"
    )
    return {
        "routing": routing,
        "learning_tag": learning_tag,
        "mode": "static",
        "sections": sections,
        "videos": videos,
        "socratic_seed_message": None,
    }
