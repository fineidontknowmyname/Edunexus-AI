from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.models.db import (
    Chunk,
    Misconception,
    PrerequisiteMap,
    QuizQuestion,
    Subject,
    TopicMastery,
)

_DRAFT_PROMPT = (
    "You are given the syllabus for a course. Extract the list of teachable topics, grouped "
    "roughly by module/unit order. For each topic give a one-sentence description and, where the "
    "syllabus makes it clear, which other topics in this same list it requires as prerequisites "
    "and which it is conceptually related to.\n\n"
    "Return ONLY a JSON array, no prose, no markdown. Each item:\n"
    '{{"topic": str, "description": str, "requires": [topic names], "related_concepts": [topic names]}}\n'
    "Every name in requires/related_concepts MUST be the exact 'topic' of another item.\n"
    "Aim for 8-30 topics. Keep names short (2-5 words).\n\n"
    "Syllabus:\n{syllabus}"
)


def _parse_json_array(raw: str) -> list[dict[str, Any]]:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"Could not parse topic JSON from LLM output: {raw[:200]!r}")


async def draft_from_syllabus(syllabus_text: str) -> list[dict[str, Any]]:
    from backend.llm.model_pool import model_pool
    from backend.services import rag_service

    provider, model_idx = model_pool.get_provider()
    prompt = _DRAFT_PROMPT.format(syllabus=syllabus_text[:12000])

    parsed: list[dict[str, Any]] | None = None
    raw = ""
    for attempt in range(2):
        raw = await provider.generate(prompt, max_tokens=2500)
        try:
            parsed = _parse_json_array(raw)
            break
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"[TOPIC DRAFT] attempt {attempt + 1} unparseable: {exc}")
            prompt += "\n\nRespond with ONLY the JSON array."

    if parsed is None:
        raise ValueError("LLM failed to produce a valid topic list.")

    model_pool.record_usage(model_idx, rag_service.estimate_tokens(prompt) + rag_service.estimate_tokens(raw))

    names = {str(item.get("topic", "")).strip() for item in parsed if item.get("topic")}
    cleaned: list[dict[str, Any]] = []
    for item in parsed:
        topic = str(item.get("topic", "")).strip()
        if not topic:
            continue
        cleaned.append(
            {
                "topic": topic[:500],
                "description": (str(item.get("description", "")).strip() or None),
                "requires": [r for r in map(str, item.get("requires", []) or []) if r in names and r != topic],
                "related_concepts": [
                    r for r in map(str, item.get("related_concepts", []) or []) if r in names and r != topic
                ],
            }
        )
    print(f"[TOPIC DRAFT] drafted {len(cleaned)} topics")
    return cleaned


def _validate_edges(topics: list[dict[str, Any]]) -> None:
    names = {t["topic"] for t in topics}
    for t in topics:
        for edge_field in ("requires", "related_concepts"):
            for ref in t.get(edge_field, []):
                if ref not in names:
                    raise ValueError(
                        f"Topic '{t['topic']}' {edge_field} references unknown topic '{ref}'."
                    )
            if t["topic"] in t.get(edge_field, []):
                raise ValueError(f"Topic '{t['topic']}' cannot reference itself in {edge_field}.")


def confirm(db: Session, subject_id: str, topics: list[dict[str, Any]], created_by: str) -> list[PrerequisiteMap]:
    subject = db.get(Subject, subject_id)
    if subject is None:
        raise ValueError(f"Subject '{subject_id}' not found.")

    seen: set[str] = set()
    for t in topics:
        name = t["topic"].strip()
        if not name:
            raise ValueError("Topic name cannot be empty.")
        if name.lower() in seen:
            raise ValueError(f"Duplicate topic '{name}'.")
        seen.add(name.lower())
    _validate_edges(topics)

    db.query(PrerequisiteMap).filter(PrerequisiteMap.subject_id == subject_id).delete()
    rows: list[PrerequisiteMap] = []
    for t in topics:
        row = PrerequisiteMap(
            subject_id=subject_id,
            subject=subject.name,
            topic=t["topic"].strip()[:500],
            description=(t.get("description") or None),
            requires=list(t.get("requires", [])),
            related_concepts=list(t.get("related_concepts", [])),
            created_by=created_by,
        )
        db.add(row)
        rows.append(row)
    db.commit()
    bump_anchor_version(subject_id)
    print(f"[TOPIC GRAPH] confirmed {len(rows)} topics for subject {subject_id}")
    return rows


def read_graph(db: Session, subject_id: str) -> list[dict[str, Any]]:
    rows = (
        db.query(PrerequisiteMap)
        .filter(PrerequisiteMap.subject_id == subject_id)
        .order_by(PrerequisiteMap.created_at, PrerequisiteMap.topic)
        .all()
    )
    return [
        {
            "topic": r.topic,
            "description": r.description,
            "requires": list(r.requires or []),
            "related_concepts": list(r.related_concepts or []),
        }
        for r in rows
    ]


def rename_topic(db: Session, subject_id: str, old_topic: str, new_topic: str) -> None:
    old_topic = old_topic.strip()
    new_topic = new_topic.strip()[:500]
    if not new_topic:
        raise ValueError("New topic name cannot be empty.")

    row = (
        db.query(PrerequisiteMap)
        .filter(PrerequisiteMap.subject_id == subject_id, PrerequisiteMap.topic == old_topic)
        .first()
    )
    if row is None:
        raise ValueError(f"Topic '{old_topic}' not found for this subject.")
    if old_topic == new_topic:
        return
    clash = (
        db.query(PrerequisiteMap)
        .filter(PrerequisiteMap.subject_id == subject_id, PrerequisiteMap.topic == new_topic)
        .first()
    )
    if clash is not None:
        raise ValueError(f"Topic '{new_topic}' already exists for this subject.")

    try:
        row.topic = new_topic
        row.updated_at = datetime.utcnow()

        for edge_row in db.query(PrerequisiteMap).filter(PrerequisiteMap.subject_id == subject_id).all():
            if edge_row.requires and old_topic in edge_row.requires:
                edge_row.requires = [new_topic if x == old_topic else x for x in edge_row.requires]
            if edge_row.related_concepts and old_topic in edge_row.related_concepts:
                edge_row.related_concepts = [
                    new_topic if x == old_topic else x for x in edge_row.related_concepts
                ]

        subject_class_ids = _subject_class_ids(db, subject_id)
        if subject_class_ids:
            db.query(TopicMastery).filter(
                TopicMastery.class_id.in_(subject_class_ids), TopicMastery.topic == old_topic
            ).update({TopicMastery.topic: new_topic}, synchronize_session=False)
            db.query(Misconception).filter(
                Misconception.class_id.in_(subject_class_ids), Misconception.topic == old_topic
            ).update({Misconception.topic: new_topic}, synchronize_session=False)

        db.query(Chunk).filter(
            Chunk.subject_id == subject_id, Chunk.topic == old_topic
        ).update({Chunk.topic: new_topic}, synchronize_session=False)

        if subject_class_ids:
            from backend.models.db import Quiz

            quiz_ids = [
                row[0]
                for row in db.query(Quiz.id).filter(Quiz.class_id.in_(subject_class_ids)).all()
            ]
            if quiz_ids:
                db.query(QuizQuestion).filter(
                    QuizQuestion.quiz_id.in_(quiz_ids), QuizQuestion.topic == old_topic
                ).update({QuizQuestion.topic: new_topic}, synchronize_session=False)

        db.commit()
        bump_anchor_version(subject_id)
        print(f"[TOPIC GRAPH] renamed '{old_topic}' -> '{new_topic}' for subject {subject_id}")
    except Exception:
        db.rollback()
        raise


def _subject_class_ids(db: Session, subject_id: str) -> list[Any]:
    from backend.models.db import Class

    return [row[0] for row in db.query(Class.id).filter(Class.subject_id == subject_id).all()]


_anchor_cache: dict[str, tuple[int, list[str], list[list[float]]]] = {}
_anchor_version: dict[str, int] = {}


def bump_anchor_version(subject_id: str) -> None:
    _anchor_version[subject_id] = _anchor_version.get(subject_id, 0) + 1


def topic_anchors(db: Session, subject_id: str, embedding_model: Any) -> tuple[list[str], list[list[float]]]:
    version = _anchor_version.get(subject_id, 0)
    cached = _anchor_cache.get(subject_id)
    if cached is not None and cached[0] == version:
        return cached[1], cached[2]

    from backend.pipeline.embedder import embed_texts

    rows = db.query(PrerequisiteMap).filter(PrerequisiteMap.subject_id == subject_id).all()
    names = [r.topic for r in rows]
    if not names:
        _anchor_cache[subject_id] = (version, [], [])
        return [], []

    anchor_texts = [
        f"{r.topic}. {r.description}" if r.description else r.topic for r in rows
    ]
    vectors = embed_texts(anchor_texts, model=embedding_model)
    _anchor_cache[subject_id] = (version, names, vectors)
    print(f"[TOPIC GRAPH] embedded {len(names)} topic anchors for subject {subject_id}")
    return names, vectors
