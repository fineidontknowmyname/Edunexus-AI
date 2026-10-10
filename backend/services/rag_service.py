from typing import Any

from sqlalchemy.orm import Session

from backend.core import topic_graph
from backend.llm.model_pool import LLMProvider, model_pool
from backend.llm.prompts import SYSTEM_PROMPT
from backend.models.db import Chunk, Document

SIMILARITY_CURRICULUM_THRESHOLD = 0.35
TOP_K_CHUNKS = 3
GRAPH_EXPANSION_K = 2

TIER_DESCRIPTIONS = {
    "strong": "confident with this material",
    "moderate_weak": "still building confidence on a few topics",
    "significant_gaps": "finding several topics difficult",
}


def taught_chapters_from_syllabus(syllabus: dict[str, str]) -> list[int]:
    chapters = []
    for chapter_str, status in syllabus.items():
        if status == "taught":
            try:
                chapters.append(int(chapter_str))
            except ValueError:
                continue
    return chapters


def _scoped_query(db: Session, distance_expr, class_id: str, subject: str | None, subject_id: str | None):
    query = (
        db.query(Chunk, distance_expr.label("distance"))
        .join(Document, Chunk.document_id == Document.id)
        .filter(Document.class_id == class_id, Document.deleted == False)  # noqa: E712
    )
    if subject_id:
        return query.filter(Chunk.subject_id == subject_id)
    if subject:
        return query.filter(Chunk.subject == subject)
    return query


def retrieve_chunks(
    db: Session,
    subject: str | None,
    query_vector: list[float],
    top_k: int = TOP_K_CHUNKS,
    chapter_scope: list[int] | None = None,
    subject_id: str | None = None,
    class_id: str | None = None,
) -> list[tuple[Chunk, float]]:
    if class_id is None:
        raise ValueError("Curriculum retrieval must be scoped to a class.")
    distance_expr = Chunk.embedding.cosine_distance(query_vector)

    results: list[tuple[Chunk, float]] = []
    if chapter_scope:
        rows = (
            _scoped_query(db, distance_expr, class_id, subject, subject_id)
            .filter(Chunk.chapter.in_(chapter_scope))
            .order_by(distance_expr)
            .limit(top_k)
            .all()
        )
        results = [(chunk, 1 - distance) for chunk, distance in rows]

    if not results:
        rows = (
            _scoped_query(db, distance_expr, class_id, subject, subject_id)
            .order_by(distance_expr)
            .limit(top_k)
            .all()
        )
        results = [(chunk, 1 - distance) for chunk, distance in rows]

    top_sim = results[0][1] if results else 0.0
    print(f"[RAG] Retrieved {len(results)} chunk(s) for class={class_id} subject={subject_id} | top_similarity={top_sim:.3f}")
    return results


def retrieve_graph_expanded(
    db: Session,
    query_vector: list[float],
    query_topic: str | None,
    subject: str | None,
    subject_id: str | None,
    chapter_scope: list[int] | None = None,
    class_id: str | None = None,
) -> tuple[list[tuple[Chunk, float]], list[str]]:
    primary = retrieve_chunks(
        db, subject, query_vector, chapter_scope=chapter_scope, subject_id=subject_id, class_id=class_id
    )

    if not subject_id or not query_topic:
        return primary, []

    neighbor_topics = topic_graph.neighbors(db, subject_id, query_topic)
    if not neighbor_topics:
        return primary, []

    have_ids = {c.id for c, _ in primary}
    distance_expr = Chunk.embedding.cosine_distance(query_vector)
    extra_rows = (
        _scoped_query(db, distance_expr, class_id, subject, subject_id)
        .filter(Chunk.topic.in_(neighbor_topics))
        .order_by(distance_expr)
        .limit(GRAPH_EXPANSION_K)
        .all()
    )
    contributed: list[str] = []
    merged = list(primary)
    for chunk, distance in extra_rows:
        if chunk.id in have_ids:
            continue
        merged.append((chunk, 1 - distance))
        contributed.append(chunk.topic)
    return merged, contributed


def determine_source_type(top_similarity: float) -> str:
    return "curriculum" if top_similarity >= SIMILARITY_CURRICULUM_THRESHOLD else "general_knowledge"


def _personal_block(
    class_context: dict[str, Any], student_context: dict[str, Any], session_mode: str, query_topic: str | None
) -> str:
    weak = ", ".join(student_context["weak_topics"][:3]) or "none"
    strong = ", ".join(student_context["strong_topics"][:3]) or "none"
    recent_misconception = (
        student_context["misconceptions"][0]["description"] if student_context["misconceptions"] else "none"
    )
    upcoming = student_context.get("upcoming_focus")
    assessment_line = (
        f"{upcoming['assessment_name']} in {upcoming['days_remaining']} days" if upcoming else "none scheduled"
    )
    mastery_entry = student_context["mastery"].get(query_topic) if query_topic else None
    mastery_line = (
        f"{query_topic}={mastery_entry['score']:.2f}" if mastery_entry else "unknown (no prior attempts)"
    )
    educator_note = student_context.get("latest_educator_note")
    return (
        f"Subject: {class_context.get('subject') or 'this subject'} | Mode: {session_mode}\n"
        f"Student: weak=[{weak}] strong=[{strong}]\n"
        f"Topic mastery score: {mastery_line}\n"
        f"Recent misconception: {recent_misconception}\n"
        f"Assessment: {assessment_line}"
        + (f"\nTeacher note: {educator_note}" if educator_note else "")
    )


def _generic_block(class_context: dict[str, Any], session_mode: str, context_tier: str | None) -> str:
    level = TIER_DESCRIPTIONS.get(context_tier or "", "at an unknown level")
    return (
        f"Subject: {class_context.get('subject') or 'this subject'} | Mode: {session_mode}\n"
        f"Student level: {level}. Do not refer to any individual student's records."
    )


def build_prompt(
    class_context: dict[str, Any],
    student_context: dict[str, Any],
    rules: list[str],
    chunks_with_sim: list[tuple[Chunk, float]],
    history: list[dict[str, str]],
    query: str,
    session_mode: str,
    query_topic: str | None,
    system_prompt: str = SYSTEM_PROMPT,
    personalized: bool = True,
    context_tier: str | None = None,
) -> str:
    system_block = (
        _personal_block(class_context, student_context, session_mode, query_topic)
        if personalized
        else _generic_block(class_context, session_mode, context_tier)
    )
    rules_block = "\n".join(f"- {r}" for r in rules) if rules else "None."
    chunks_block = (
        "\n\n".join(
            f"[Unit {chunk.unit}, Chapter {chunk.chapter}]\n{chunk.text}" for chunk, _sim in chunks_with_sim
        )
        if chunks_with_sim
        else "None retrieved."
    )
    history_block = (
        "\n".join(f"{turn['role']}: {turn['content']}" for turn in history[-3:]) if history and personalized else "None."
    )
    return (
        f"{system_prompt}\n\n"
        f"{system_block}\n\n"
        f"Active guidance:\n{rules_block}\n\n"
        f"Curriculum context:\n{chunks_block}\n\n"
        f"Conversation history:\n{history_block}\n\n"
        f"Student message: {query}"
    )


def get_llm_provider() -> tuple[LLMProvider, int]:
    return model_pool.get_provider()


def estimate_tokens(text: str) -> int:
    return len(text.split())
