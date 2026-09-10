from __future__ import annotations

from sqlalchemy.orm import Session

from backend.models.db import PrerequisiteMap


def neighbors(db: Session, subject_id: str, topic: str) -> set[str]:
    if not topic:
        return set()

    rows = db.query(PrerequisiteMap).filter(PrerequisiteMap.subject_id == subject_id).all()
    out: set[str] = set()
    for row in rows:
        edges = list(row.requires or []) + list(row.related_concepts or [])
        if row.topic == topic:
            out.update(edges)
        elif topic in edges:
            out.add(row.topic)
    out.discard(topic)
    return out
