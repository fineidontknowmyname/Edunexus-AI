from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

# Strict YouTube domains
ALLOWED_HOSTNAMES = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "music.youtube.com",
}

YOUTUBE_VIDEO_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{11}$")

# Pre-seeded canonical videos for Operating Systems topics (used as high-reliability cache and offline fallback)
CANONICAL_OS_VIDEOS: dict[str, list[dict[str, Any]]] = {
    "Process Concepts": [
        {
            "video_id": "2i2N_Qo_VbQ",
            "title": "Processes in Operating Systems - Process Control Block (PCB)",
            "channel": "Gate Smashers",
            "duration": "10:14",
            "thumbnail": "https://i.ytimg.com/vi/2i2N_Qo_VbQ/hqdefault.jpg",
            "source": "auto",
            "embeddable": True,
        }
    ],
    "CPU Scheduling": [
        {
            "video_id": "EWkqlLsmeps",
            "title": "Introduction to CPU Scheduling Algorithms",
            "channel": "Gate Smashers",
            "duration": "11:22",
            "thumbnail": "https://i.ytimg.com/vi/EWkqlLsmeps/hqdefault.jpg",
            "source": "auto",
            "embeddable": True,
        }
    ],
    "FCFS": [
        {
            "video_id": "MZdVAVMgmPA",
            "title": "First Come First Serve (FCFS) Scheduling with Examples",
            "channel": "Gate Smashers",
            "duration": "12:45",
            "thumbnail": "https://i.ytimg.com/vi/MZdVAVMgmPA/hqdefault.jpg",
            "source": "auto",
            "embeddable": True,
        }
    ],
    "SJF": [
        {
            "video_id": "vc_iPT5KqE8",
            "title": "Shortest Job First (SJF) Preemptive & Non-Preemptive Scheduling",
            "channel": "Gate Smashers",
            "duration": "14:10",
            "thumbnail": "https://i.ytimg.com/vi/vc_iPT5KqE8/hqdefault.jpg",
            "source": "auto",
            "embeddable": True,
        }
    ],
    "Round Robin": [
        {
            "video_id": "TxjIlNYRZ5w",
            "title": "Round Robin CPU Scheduling Algorithm with Time Quantum",
            "channel": "Gate Smashers",
            "duration": "13:30",
            "thumbnail": "https://i.ytimg.com/vi/TxjIlNYRZ5w/hqdefault.jpg",
            "source": "auto",
            "embeddable": True,
        }
    ],
    "Process Synchronization": [
        {
            "video_id": "ph2aurbaMzk",
            "title": "Process Synchronization - Critical Section Problem & Semaphores",
            "channel": "Gate Smashers",
            "duration": "15:05",
            "thumbnail": "https://i.ytimg.com/vi/ph2aurbaMzk/hqdefault.jpg",
            "source": "auto",
            "embeddable": True,
        }
    ],
    "Deadlock Detection": [
        {
            "video_id": "UVo9myLmEHQ",
            "title": "Deadlock in Operating System - Conditions & Banker's Algorithm",
            "channel": "Gate Smashers",
            "duration": "16:20",
            "thumbnail": "https://i.ytimg.com/vi/UVo9myLmEHQ/hqdefault.jpg",
            "source": "auto",
            "embeddable": True,
        }
    ],
    "Memory Management": [
        {
            "video_id": "s-tT_GvUe6k",
            "title": "Memory Management in OS - Contiguous vs Non-Contiguous Allocation",
            "channel": "Gate Smashers",
            "duration": "12:15",
            "thumbnail": "https://i.ytimg.com/vi/s-tT_GvUe6k/hqdefault.jpg",
            "source": "auto",
            "embeddable": True,
        }
    ],
    "Paging": [
        {
            "video_id": "pJ6qrCB8pZw",
            "title": "Paging in Operating System - Page Table, Frames & Address Translation",
            "channel": "Gate Smashers",
            "duration": "14:50",
            "thumbnail": "https://i.ytimg.com/vi/pJ6qrCB8pZw/hqdefault.jpg",
            "source": "auto",
            "embeddable": True,
        }
    ],
}


def extract_video_id(url: str) -> str | None:
    """
    Validates the YouTube URL and returns the 11-character video ID.
    Rejects malformed URLs, domain spoofing, and unknown query structures.
    """
    if not url or not isinstance(url, str):
        return None
    cleaned = url.strip()
    try:
        parsed = urlparse(cleaned)
    except Exception:
        return None

    hostname = (parsed.hostname or "").lower()
    if hostname not in ALLOWED_HOSTNAMES:
        return None

    path = parsed.path
    video_id: str | None = None

    if hostname == "youtu.be":
        # Format: youtu.be/VIDEO_ID
        candidate = path.lstrip("/").split("/")[0]
        if YOUTUBE_VIDEO_ID_REGEX.match(candidate):
            video_id = candidate
    else:
        # Format: youtube.com/watch?v=VIDEO_ID or youtube.com/shorts/VIDEO_ID
        if path.startswith("/shorts/"):
            candidate = path.split("/shorts/")[1].split("/")[0]
            if YOUTUBE_VIDEO_ID_REGEX.match(candidate):
                video_id = candidate
        elif path.startswith("/watch"):
            query_params = parse_qs(parsed.query)
            v_list = query_params.get("v")
            if v_list and YOUTUBE_VIDEO_ID_REGEX.match(v_list[0]):
                video_id = v_list[0]
        elif path.startswith("/embed/"):
            candidate = path.split("/embed/")[1].split("/")[0]
            if YOUTUBE_VIDEO_ID_REGEX.match(candidate):
                video_id = candidate

    return video_id


def build_canonical_youtube_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def build_nocookie_embed_url(video_id: str) -> str:
    return f"https://www.youtube-nocookie.com/embed/{video_id}"


def parse_iso8601_duration(duration_str: str) -> str:
    """Parses ISO 8601 duration (e.g. 'PT12M34S') into '12:34' format."""
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration_str)
    if not match:
        return "Video"
    hours, minutes, seconds = match.groups()
    h = int(hours) if hours else 0
    m = int(minutes) if minutes else 0
    s = int(seconds) if seconds else 0
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def fetch_youtube_metadata(video_id: str) -> dict[str, Any]:
    """
    Fetches real metadata (title, channel, duration, thumbnail, embeddability)
    for a validated video ID using YouTube Data API v3 if configured, with
    oEmbed and local fallback.
    """
    settings = get_settings()
    api_key = getattr(settings, "youtube_api_key", None) or ""

    # 1. Attempt YouTube Data API v3
    if api_key.strip():
        try:
            url = "https://www.googleapis.com/youtube/v3/videos"
            params = {
                "part": "snippet,contentDetails,status",
                "id": video_id,
                "key": api_key.strip(),
            }
            with httpx.Client(timeout=4.0) as client:
                res = client.get(url, params=params)
                if res.status_code == 200:
                    data = res.json()
                    items = data.get("items", [])
                    if items:
                        item = items[0]
                        snippet = item.get("snippet", {})
                        content_details = item.get("contentDetails", {})
                        status_details = item.get("status", {})

                        title = snippet.get("title", f"YouTube Video ({video_id})")
                        channel = snippet.get("channelTitle", "YouTube Channel")
                        duration_raw = content_details.get("duration", "")
                        duration = parse_iso8601_duration(duration_raw) if duration_raw else "Video"

                        thumbnails = snippet.get("thumbnails", {})
                        thumb_obj = thumbnails.get("high") or thumbnails.get("medium") or thumbnails.get("default") or {}
                        thumbnail_url = thumb_obj.get("url") or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

                        embeddable = status_details.get("embeddable", True)

                        return {
                            "video_id": video_id,
                            "title": title,
                            "channel": channel,
                            "duration": duration,
                            "thumbnail": thumbnail_url,
                            "embeddable": embeddable,
                            "url": build_canonical_youtube_url(video_id),
                        }
        except Exception as exc:
            logger.warning("YouTube Data API v3 request failed: %s; falling back to oEmbed", exc)

    # 2. Attempt YouTube oEmbed API (does not require an API key)
    try:
        oembed_url = "https://www.youtube.com/oembed"
        params = {
            "url": build_canonical_youtube_url(video_id),
            "format": "json",
        }
        with httpx.Client(timeout=3.0) as client:
            res = client.get(oembed_url, params=params)
            if res.status_code == 200:
                data = res.json()
                title = data.get("title", f"YouTube Video ({video_id})")
                channel = data.get("author_name", "YouTube")
                thumb = data.get("thumbnail_url") or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                return {
                    "video_id": video_id,
                    "title": title,
                    "channel": channel,
                    "duration": "Video",
                    "thumbnail": thumb,
                    "embeddable": True,
                    "url": build_canonical_youtube_url(video_id),
                }
    except Exception as exc:
        logger.warning("YouTube oEmbed request failed: %s; using deterministic fallback", exc)

    # 3. Deterministic verified fallback
    return {
        "video_id": video_id,
        "title": f"Educational Video ({video_id})",
        "channel": "YouTube Educator",
        "duration": "Video",
        "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        "embeddable": True,
        "url": build_canonical_youtube_url(video_id),
    }


def discover_topic_videos(topic: str, subject_name: str | None = None) -> list[dict[str, Any]]:
    """
    Retrieves educational YouTube resources for a topic.
    Returns cached canonical videos or queries YouTube Data API if configured.
    Never falls back to hardcoded Operating Systems topics unless the subject is Operating Systems.
    """
    # 1. Check canonical cache only if subject is explicitly Operating Systems
    is_os_subject = False
    if subject_name:
        norm_subj = subject_name.strip().lower()
        is_os_subject = norm_subj in ("operating systems", "os")

    if is_os_subject:
        for canonical_topic, videos in CANONICAL_OS_VIDEOS.items():
            if canonical_topic.casefold() in topic.casefold() or topic.casefold() in canonical_topic.casefold():
                return [
                    {
                        **v,
                        "url": build_canonical_youtube_url(v["video_id"]),
                        "source": "auto",
                    }
                    for v in videos
                ]

    # 2. If Data API is available and topic wasn't pre-cached, query YouTube search
    settings = get_settings()
    api_key = getattr(settings, "youtube_api_key", None) or ""
    if api_key.strip():
        try:
            subject_term = f" {subject_name.strip()}" if subject_name and subject_name.strip() else ""
            query = f"{topic}{subject_term} tutorial"
            url = "https://www.googleapis.com/youtube/v3/search"
            params = {
                "part": "snippet",
                "q": query,
                "type": "video",
                "maxResults": 2,
                "key": api_key.strip(),
            }
            with httpx.Client(timeout=4.0) as client:
                res = client.get(url, params=params)
                if res.status_code == 200:
                    items = res.json().get("items", [])
                    results = []
                    for item in items:
                        vid = item.get("id", {}).get("videoId")
                        if not vid:
                            continue
                        snippet = item.get("snippet", {})
                        results.append({
                            "video_id": vid,
                            "title": snippet.get("title", f"{topic} Overview"),
                            "channel": snippet.get("channelTitle", "YouTube Educator"),
                            "duration": "Video",
                            "thumbnail": (
                                snippet.get("thumbnails", {}).get("high", {}).get("url")
                                or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
                            ),
                            "source": "auto",
                            "embeddable": True,
                            "url": build_canonical_youtube_url(vid),
                        })
                    if results:
                        return results
        except Exception as exc:
            logger.warning("YouTube Search API failed: %s", exc)

    # 3. Default fallback for arbitrary un-cached topics
    return []
