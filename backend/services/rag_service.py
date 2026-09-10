from typing import Any

from sqlalchemy.orm import Session

from backend.core import topic_graph
from backend.llm.model_pool import LLMProvider, model_pool
from backend.llm.prompts import SYSTEM_PROMPT
from backend.models.db import Chunk

SIMILARITY_CURRICULUM_THRESHOLD = 0.55
TOP_K_CHUNKS = 3
GRAPH_EXPANSION_K = 2


def taught_chapters_from_syllabus(syllabus: dict[str, str]) -> list[int]:
    chapters = []
    for chapter_str, status in syllabus.items():
        if status == "taught":
            try:
                chapters.append(int(chapter_str))
            except ValueError:
                continue
    return chapters


def _subject_filter(subject: str | None, subject_id: str | None):
    if subject_id:
        return Chunk.subject_id == subject_id
    return Chunk.subject == subject


def retrieve_chunks(
    db: Session,
    subject: str | None,
    query_vector: list[float],
    top_k: int = TOP_K_CHUNKS,
    chapter_scope: list[int] | None = None,
    subject_id: str | None = None,
) -> list[tuple[Chunk, float]]:
    distance_expr = Chunk.embedding.cosine_distance(query_vector)
    base_filter = _subject_filter(subject, subject_id)
    query = db.query(Chunk, distance_expr.label("distance")).filter(base_filter)

    if chapter_scope:
        query = query.filter(Chunk.chapter.in_(chapter_scope))
        print(f"[RAG] Retrieval scoped to taught chapters: {chapter_scope}")
    else:
        print("[RAG] No taught chapters recorded on syllabus yet — searching whole subject corpus")

    rows = query.order_by(distance_expr).limit(top_k).all()
    results = [(chunk, 1 - distance) for chunk, distance in rows]

    if chapter_scope and not results:
        print("[RAG] Chapter-scoped search returned nothing — falling back to whole-subject search")
        rows = (
            db.query(Chunk, distance_expr.label("distance"))
            .filter(base_filter)
            .order_by(distance_expr)
            .limit(top_k)
            .all()
        )
        results = [(chunk, 1 - distance) for chunk, distance in rows]

    top_sim = results[0][1] if results else 0.0
    print(f"[RAG] Retrieved {len(results)} chunk(s) for subject={subject!r}/{subject_id} | top_similarity={top_sim:.3f}")
    return results


def retrieve_graph_expanded(
    db: Session,
    query_vector: list[float],
    query_topic: str | None,
    subject: str | None,
    subject_id: str | None,
    chapter_scope: list[int] | None = None,
) -> tuple[list[tuple[Chunk, float]], list[str]]:
    primary = retrieve_chunks(
        db, subject, query_vector, chapter_scope=chapter_scope, subject_id=subject_id
    )

    if not subject_id or not query_topic:
        return primary, []

    neighbor_topics = topic_graph.neighbors(db, subject_id, query_topic)
    if not neighbor_topics:
        return primary, []

    have_ids = {c.id for c, _ in primary}
    distance_expr = Chunk.embedding.cosine_distance(query_vector)
    extra_rows = (
        db.query(Chunk, distance_expr.label("distance"))
        .filter(Chunk.subject_id == subject_id, Chunk.topic.in_(neighbor_topics))
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
    if contributed:
        print(f"[RAG] Graph expansion added {len(contributed)} chunk(s) from neighbour topics: {contributed}")
    return merged, contributed


def determine_source_type(top_similarity: float) -> str:
    source_type = "curriculum" if top_similarity >= SIMILARITY_CURRICULUM_THRESHOLD else "general_knowledge"
    print(f"[RAG] Source type determined: {source_type} (top_similarity={top_similarity:.3f}, threshold={SIMILARITY_CURRICULUM_THRESHOLD})")
    return source_type


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

    system_block = (
        f"Subject: {class_context.get('subject') or 'this subject'} | Mode: {session_mode}\n"
        f"Student: weak=[{weak}] strong=[{strong}]\n"
        f"Topic mastery score: {mastery_line}\n"
        f"Recent misconception: {recent_misconception}\n"
        f"Assessment: {assessment_line}"
        + (f"\nTeacher note: {educator_note}" if educator_note else "")
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
        "\n".join(f"{turn['role']}: {turn['content']}" for turn in history[-3:]) if history else "None."
    )

    prompt = (
        f"{system_prompt}\n\n"
        f"{system_block}\n\n"
        f"Active guidance:\n{rules_block}\n\n"
        f"Curriculum context:\n{chunks_block}\n\n"
        f"Conversation history:\n{history_block}\n\n"
        f"Student message: {query}"
    )
    print(f"[RAG] Prompt built — approx {estimate_tokens(prompt)} tokens (word-count proxy)")
    return prompt


def get_llm_provider() -> tuple[LLMProvider, int]:
    provider, model_idx = model_pool.get_provider()
    print(f"[RAG] LLM provider selected: {type(provider).__name__} (model_idx={model_idx})")
    return provider, model_idx


def estimate_tokens(text: str) -> int:
    return len(text.split())
