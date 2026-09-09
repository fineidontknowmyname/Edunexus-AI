"""Per-subject Topic Graph access.

New (Phase 1, multi-subject): the Topic Graph — topics plus prerequisite and
related-concept edges — lives in the ``prerequisite_map`` table, one row per
topic, scoped by ``subject_id``. It is drafted from an uploaded syllabus and
confirmed by the educator (see ``services.topic_graph_service``). Use the
``*_db`` helpers below; they take a ``subject_id`` and never fall back to any
bundled file or default subject.

Legacy: ``load_prerequisite_map`` / ``get_prerequisites`` still read the bundled
``data/prerequisites_*.json`` file keyed by subject *name*. These remain only for
the pre-multi-subject chat/progress code paths (context_service, progress_service)
and are removed once those are migrated to ``subject_id`` in a later chunk.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from backend.models.db import PrerequisiteMap

# --------------------------------------------------------------------------- #
# New: per-subject Topic Graph, backed by the prerequisite_map table
# --------------------------------------------------------------------------- #


def load_topic_graph_db(db: Session, subject_id: str) -> dict[str, dict]:
    """``{topic: {"description", "requires", "related_concepts"}}`` for a subject."""
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


# --------------------------------------------------------------------------- #
# Legacy: bundled-file prerequisite map, keyed by subject name
# --------------------------------------------------------------------------- #

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=16)
def load_prerequisite_map(subject: str = "") -> dict[str, list[str]]:
    if not subject:
        return {}
    filename = f"prerequisites_{subject.lower().replace(' ', '_')}.json"
    file_path = _DATA_DIR / filename
    if not file_path.exists():
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("prerequisite_map", {})


def get_prerequisites(topic: str, subject: str = "") -> list[str]:
    return load_prerequisite_map(subject).get(topic, [])
