from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from backend.models.db import PrerequisiteMap


def load_topic_graph_db(db: Session, subject_id: str) -> dict[str, dict]:
    rows = db.query(PrerequisiteMap).filter(PrerequisiteMap.subject_id == subject_id).all()
    return {
        row.topic: {
            "description": row.description or "",
            "requires": list(row.requires or []),
            "related_concepts": list(row.related_concepts or []),
        }
        for row in rows
    }


def get_prerequisites_db(db: Session, subject_id: str, topic: str) -> list[str]:
    row = (
        db.query(PrerequisiteMap)
        .filter(PrerequisiteMap.subject_id == subject_id, PrerequisiteMap.topic == topic)
        .first()
    )
    return list(row.requires or []) if row else []


def topic_names_db(db: Session, subject_id: str) -> list[str]:
    return [
        row.topic
        for row in db.query(PrerequisiteMap.topic)
        .filter(PrerequisiteMap.subject_id == subject_id)
        .all()
    ]


_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_LEGACY_FILES = {
    "operating systems": "prerequisites_os.json",
    "os": "prerequisites_os.json",
}


@lru_cache(maxsize=16)
def load_prerequisite_map(subject: str = "") -> dict[str, list[str]]:
    if not subject:
        return {}
    candidates = [
        f"prerequisites_{subject.lower().replace(' ', '_')}.json",
        _LEGACY_FILES.get(subject.lower().strip(), ""),
    ]
    for filename in candidates:
        if not filename:
            continue
        file_path = _DATA_DIR / filename
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f).get("prerequisite_map", {})
    return {}


def get_prerequisites(topic: str, subject: str = "") -> list[str]:
    return load_prerequisite_map(subject).get(topic, [])
