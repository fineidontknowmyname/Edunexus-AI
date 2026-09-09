"""Per-subject topic-graph traversal for Graph RAG.

The graph lives in ``prerequisite_map`` (one row per topic, `requires` and
`related_concepts` edge arrays). This module answers "what topics sit next to
topic X for subject S" — used by ``rag_service`` to pull chunks from neighbouring
topics after the primary vector pass. No networkx: 1-hop is a single query.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from backend.models.db import PrerequisiteMap


def neighbors(db: Session, subject_id: str, topic: str) -> set[str]:
    """1-hop neighbours of ``topic`` in the subject's graph, both directions:
    the topic's own `requires` / `related_concepts`, plus any topic that lists
    ``topic`` in its own edges."""
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
