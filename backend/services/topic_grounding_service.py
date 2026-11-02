import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.models.db import Chunk, Document, DocumentStatus, PrerequisiteMap
from backend.services import rag_service

logger = logging.getLogger(__name__)

_STOP_WORDS = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
    "is", "are", "was", "were", "be", "been", "does", "do", "did", "which",
    "what", "where", "how", "why", "following", "true", "false", "statement",
    "correct", "incorrect", "from",
}
_MIN_TOPIC_RELEVANCE = 0.24


@dataclass(frozen=True)
class TopicGrounding:
    chunks: list[tuple[Chunk, float]]

    @property
    def has_material(self) -> bool:
        return bool(self.chunks)

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)


def _topic_terms(value: str) -> list[str]:
    return [
        term
        for term in re.findall(r"[a-z0-9]+", value.casefold())
        if len(term) >= 3 and term not in _STOP_WORDS
    ]


def extract_page_number(chunk: Chunk) -> int | None:
    if chunk.page_number is not None:
        return chunk.page_number
    match = re.search(r"\[Page\s*(\d+)\]", chunk.text or "", re.IGNORECASE)
    return int(match.group(1)) if match else None


def score_chunk_substantive_relevance(
    chunk: Chunk,
    canonical_topic: str,
    subtopics: list[str],
    objectives: list[str],
) -> float:
    text = chunk.text or ""
    heading = chunk.section_heading or ""
    topic_tag = chunk.topic or ""
    combined = f"{heading} {topic_tag} {text}".casefold()
    topic_lower = canonical_topic.casefold().strip()
    terms = _topic_terms(topic_lower)
    score = 0.0

    heading_terms = set(_topic_terms(heading))
    if topic_lower and topic_lower in heading.casefold():
        score += 0.40
    elif terms and all(term in heading_terms for term in terms):
        score += 0.30

    tag_terms = set(_topic_terms(topic_tag))
    if topic_lower and topic_lower in topic_tag.casefold():
        score += 0.30
    elif terms and all(term in tag_terms for term in terms):
        score += 0.24

    text_lower = text.casefold()
    words = re.findall(r"[a-z0-9]+", text_lower)
    term_frequency = sum(words.count(term) for term in terms)
    matched_terms = sum(1 for term in terms if term in words)
    if topic_lower and topic_lower in text_lower:
        score += 0.18
    if terms:
        score += min(0.36, term_frequency * 0.06)
        score += 0.12 * matched_terms / len(terms)
    context_terms = list(
        dict.fromkeys(
            term
            for value in [*subtopics, *objectives]
            for term in _topic_terms(value)
            if term not in terms
        )
    )[:20]
    if context_terms:
        context_matches = sum(1 for term in context_terms if term in words)
        score += min(0.20, context_matches * 0.025)
        score += 0.05 * context_matches / len(context_terms)

    for subtopic in subtopics:
        if subtopic and subtopic.casefold() in combined:
            score += 0.04
    for objective in objectives:
        if objective and objective.casefold() in combined:
            score += 0.04

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    substantive = [
        part
        for part in paragraphs
        if len(re.findall(r"\b\w+\b", part)) >= 25
        and len(re.findall(r"[.!?](?:\s|$)", part)) >= 2
    ]
    score += min(0.20, len(substantive) * 0.07)
    if len(text.strip()) < 150:
        score -= 0.20

    page_number = extract_page_number(chunk)
    is_toc_or_outline = bool(
        re.search(
            r"\b(table of contents|contents|course outcomes|syllabus|course overview|course outline|module\s+[1-5]|text\s*books?|references?)\b",
            combined,
        )
    )
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    bullet_count = sum(
        1 for line in lines if re.match(r"^(?:[-*•]|\d+[.)])\s*", line)
    )
    heading_count = sum(
        1
        for line in lines
        if len(re.findall(r"\b\w+\b", line)) <= 7
        and not re.search(r"[.!?]", line)
    )
    bullet_heavy = len(lines) > 3 and bullet_count / len(lines) > 0.55
    heading_heavy = bool(lines) and heading_count / len(lines) > 0.65
    if is_toc_or_outline:
        score -= 0.55
    if page_number in (1, 2) and (
        bullet_heavy or heading_heavy or is_toc_or_outline
        or (len(text.strip()) < 300 and not re.search(r"[.!?](?:\s|$)", text))
    ):
        score -= 0.30
    if bullet_heavy or heading_heavy:
        score -= 0.25
    return score


def _near_duplicate(left: str, right: str) -> bool:
    left_words = re.findall(r"[a-z0-9]+", left.casefold())
    right_words = re.findall(r"[a-z0-9]+", right.casefold())
    if not left_words or not right_words:
        return False
    left_set, right_set = set(left_words), set(right_words)
    overlap = len(left_set & right_set)
    return overlap / min(len(left_set), len(right_set)) >= 0.94 and overlap / len(left_set | right_set) >= 0.82


def get_topic_grounding(
    db: Session,
    class_id: uuid.UUID | str,
    subject: str | None,
    subject_id: str | None,
    canonical_topic: str,
    topic_row: PrerequisiteMap | None,
    embedding_model: Any,
    top_k: int = 6,
) -> TopicGrounding:
    """Return ranked, deduplicated relevant chunks from ready documents in this class."""
    if (
        subject_id
        and topic_row
        and topic_row.subject_id
        and str(topic_row.subject_id) != str(subject_id)
    ):
        logger.warning("Skipping topic retrieval for topic id outside the class subject: %s", topic_row.id)
        return TopicGrounding([])

    subtopics = [
        item.name for item in (topic_row.subtopics or [])
    ] if topic_row else []
    objectives = [
        getattr(item, "statement", getattr(item, "objective", ""))
        for item in (topic_row.learning_objectives or [])
    ] if topic_row else []
    if topic_row and topic_row.description:
        objectives.append(topic_row.description)
    unit = topic_row.unit if topic_row else None
    source_doc_id = topic_row.source_document_id if topic_row else None

    base_query = (
        db.query(Chunk)
        .join(Document, Chunk.document_id == Document.id)
        .filter(
            Document.class_id == class_id,
            Document.deleted == False,  # noqa: E712
            Document.status == DocumentStatus.ready,
        )
    )

    anchor_parts = [canonical_topic]
    if subject:
        anchor_parts.append(f"Curriculum subject: {subject}")
    if topic_row and topic_row.description:
        anchor_parts.append(topic_row.description)
    if subtopics:
        anchor_parts.extend(subtopics)
    if objectives:
        anchor_parts.extend(objectives)
    anchor_text = " ".join(anchor_parts)
    terms = list(dict.fromkeys(_topic_terms(anchor_text)))

    conditions = [
        Chunk.section_heading.ilike(f"%{canonical_topic}%"),
        Chunk.topic.ilike(f"%{canonical_topic}%"),
        Chunk.text.ilike(f"%{canonical_topic}%"),
        Chunk.full_text.ilike(f"%{canonical_topic}%"),
    ]
    for term in terms:
        pattern = f"%{term}%"
        conditions.extend(
            [
                Chunk.section_heading.ilike(pattern),
                Chunk.topic.ilike(pattern),
                Chunk.text.ilike(pattern),
                Chunk.full_text.ilike(pattern),
            ]
        )
    if source_doc_id:
        conditions.append(Chunk.document_id == source_doc_id)

    candidates: dict[uuid.UUID, Chunk] = {
        chunk.id: chunk
        for chunk in base_query.filter(or_(*conditions)).order_by(Chunk.chunk_index).limit(1000).all()
    }
    vector_sims: dict[uuid.UUID, float] = {}
    if embedding_model:
        try:
            from backend.pipeline.embedder import embed_single

            query_vector = embed_single(anchor_text, model=embedding_model)
            for chunk, similarity in rag_service.retrieve_chunks(
                db,
                None,
                query_vector,
                top_k=max(top_k * 8, 48),
                class_id=str(class_id),
            ):
                if similarity >= 0.20 and chunk.document.status == DocumentStatus.ready:
                    candidates[chunk.id] = chunk
                    vector_sims[chunk.id] = float(similarity)
        except Exception as exc:
            logger.warning(
                "Topic vector retrieval failed; using class-scoped lexical retrieval: %s",
                exc,
            )

    if len(candidates) < top_k and unit is not None:
        for chunk in base_query.filter(Chunk.unit == unit).limit(top_k).all():
            candidates.setdefault(chunk.id, chunk)

    scored: list[tuple[Chunk, float]] = []
    for chunk in candidates.values():
        score = score_chunk_substantive_relevance(
            chunk, canonical_topic, subtopics, objectives
        )
        score += vector_sims.get(chunk.id, 0.0) * 0.30
        if source_doc_id and chunk.document_id == source_doc_id:
            score += 0.08
        if (
            topic_row
            and topic_row.source_page_number is not None
            and chunk.document_id == source_doc_id
        ):
            page_number = extract_page_number(chunk)
            if page_number is not None:
                page_distance = abs(page_number - topic_row.source_page_number)
                score += 0.18 if page_distance == 0 else 0.08 if page_distance <= 2 else 0.0
        if score >= _MIN_TOPIC_RELEVANCE:
            scored.append((chunk, round(min(1.0, max(0.0, score)), 4)))

    scored.sort(key=lambda pair: (-pair[1], str(pair[0].id)))
    unique: list[tuple[Chunk, float]] = []
    seen_text: list[str] = []
    for chunk, score in scored:
        normalized = " ".join((chunk.text or "").casefold().split())
        if not normalized or any(
            normalized == prior or _near_duplicate(normalized, prior)
            for prior in seen_text
        ):
            continue
        unique.append((chunk, score))
        seen_text.append(normalized)
        if len(unique) >= top_k:
            break
    return TopicGrounding(unique)
