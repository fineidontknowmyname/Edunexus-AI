import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.models.db import (
    Chunk,
    Class,
    Document,
    DocumentStatus,
    LearningObjective,
    PrerequisiteMap,
    QuestionCurriculumMapping,
    QuestionDifficulty,
    QuestionType,
    Quiz,
    QuizAttempt,
    QuizAttemptAnswer,
    QuizQuestion,
    ReviewStatus,
    SyllabusSubtopic,
    User,
)
from backend.services import context_service, misconception_service, rag_service, routing_service

logger = logging.getLogger(__name__)

QUIZ_GENERATION_PROMPT_TEMPLATE = (
    "Generate {n} multiple-choice questions testing understanding of the curriculum content below. "
    "Return ONLY a JSON array, no other text, no markdown formatting. "
    "Each item: {{\"question\": str, \"options\": [4 strings], \"correct_answer\": str (must exactly match one option), "
    "\"difficulty\": \"easy\"|\"medium\"|\"hard\"}}.\n\n"
    "Curriculum content:\n{content}"
)

QUIZ_GENERATION_PROMPT_V2 = (
    "You are an expert curriculum assessor generating questions to test student understanding of the curriculum materials below.\n"
    "Generate {n} assessment questions strictly testing understanding based ONLY on the curriculum material below.\n\n"
    "Curriculum Sources:\n{content}\n\n"
    "{avoid_block}"
    "Requirements:\n"
    "1. Curriculum Alignment: Every question must directly test concepts using facts from the provided sources. Do not hallucinate or invent facts not present in the sources.\n"
    "2. Pedagogical Diversity: Questions must cover different concepts and mechanisms, providing a balanced mix across conceptual comprehension, analytical comparison, and factual recall.\n"
    "3. Question Formats: Include 'single_choice', 'multiple_choice' (with 2 or more correct choices), or 'true_false' (mostly single_choice).\n"
    "4. Difficulty Calibration: 'easy', 'medium', or 'hard'.\n"
    "5. Bloom's Taxonomy Level: Tag each question with 'bloom_level': 'remember' | 'understand' | 'apply' | 'analyze'.\n"
    "6. Provenance Attribution: For each question, specify the source chunk number that directly supports the answer ('chunk_index': int, 1-based Source number).\n"
    "7. Explanations: Provide a concise explanation grounded strictly in the source text explaining why the correct answer is right and why distractors are wrong.\n"
    "8. Duplication Avoidance: Ensure every question tests a distinct concept. Do not ask repetitive variations.\n"
    "9. Return ONLY a valid JSON array, no preamble, no markdown formatting.\n\n"
    "Each JSON item must have this structure:\n"
    "{{\n"
    "  \"question_text\": \"Question text here\",\n"
    "  \"question_type\": \"single_choice\" | \"multiple_choice\" | \"true_false\",\n"
    "  \"options\": [\"Option 1\", \"Option 2\", \"Option 3\", \"Option 4\"] (or [\"True\", \"False\"] for true_false),\n"
    "  \"correct_answer\": \"Exact matching option\" (or [\"Opt 1\", \"Opt 2\"] for multiple_choice),\n"
    "  \"difficulty\": \"easy\" | \"medium\" | \"hard\",\n"
    "  \"bloom_level\": \"remember\" | \"understand\" | \"apply\" | \"analyze\",\n"
    "  \"explanation\": \"Brief explanation grounded in the text justifying why the answer is right\",\n"
    "  \"chunk_index\": 1\n"
    "}}"
)

TOPIC_QUIZ_PROMPT_TEMPLATE = (
    "You are an expert curriculum assessor generating diagnostic questions for a student on the topic: '{topic}'.\n"
    "Generate {n} assessment questions strictly testing understanding of this topic based ONLY on the curriculum material below.\n\n"
    "Curriculum Sources:\n{content}\n\n"
    "Requirements:\n"
    "1. Topic Alignment: Every question must directly test '{topic}' using facts from the provided sources. Do not hallucinate or invent facts not present in the sources.\n"
    "2. Pedagogical Diversity: Provide a balanced mix across these cognitive dimensions:\n"
    "   - Conceptual Understanding: Comprehension of core principles and mechanisms.\n"
    "   - Application & Scenario: Applying concepts to realistic scenarios or problem situations.\n"
    "   - Analytical & Comparative: Comparing mechanisms, distinguishing causes from effects, or evaluating errors.\n"
    "   - Factual & Definitional: Accurate terminology, cellular locations, and structural components.\n"
    "3. Question Formats: Include 'single_choice', 'multiple_choice' (with 2 or more correct choices), or 'true_false'.\n"
    "4. Difficulty Calibration:\n"
    "   - 'easy': Direct recall, terminology, or basic identification.\n"
    "   - 'medium': Conceptual comprehension, comparing two components, or explaining why a process occurs.\n"
    "   - 'hard': Multi-step deduction, scenario-based problem solving, or analyzing consequences of an intervention.\n"
    "5. Bloom's Taxonomy Level: Tag each question with 'bloom_level': 'remember' | 'understand' | 'apply' | 'analyze'.\n"
    "6. Provenance Attribution: For each question, specify the source chunk number that directly supports the answer ('chunk_index': int, 1-based).\n"
    "7. Explanations: Provide a concise explanation grounded strictly in the source text explaining why the correct answer is right and why distractors are wrong.\n"
    "8. Duplication Avoidance: Ensure every question tests a distinct facet or subtopic. Do not ask repetitive variations of the same question.\n"
    "9. Return ONLY a valid JSON array, no preamble, no markdown formatting.\n\n"
    "Each JSON item must have this structure:\n"
    "{{\n"
    "  \"question\": \"Question text here\",\n"
    "  \"question_type\": \"single_choice\" | \"multiple_choice\" | \"true_false\",\n"
    "  \"options\": [\"Option 1\", \"Option 2\", \"Option 3\", \"Option 4\"] (or [\"True\", \"False\"] for true_false),\n"
    "  \"correct_answer\": \"Exact matching option\" (or [\"Opt 1\", \"Opt 2\"] for multiple_choice),\n"
    "  \"difficulty\": \"easy\" | \"medium\" | \"hard\",\n"
    "  \"bloom_level\": \"remember\" | \"understand\" | \"apply\" | \"analyze\",\n"
    "  \"explanation\": \"Brief explanation grounded in the text\",\n"
    "  \"chunk_index\": 1\n"
    "}}"
)

_STOP_WORDS = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
    "is", "are", "was", "were", "be", "been", "does", "do", "did", "which",
    "what", "where", "how", "why", "following", "true", "false", "statement",
    "correct", "incorrect", "cell", "describe", "explains", "regarding", "from"
}


def _tokenize_meaningful(text: str) -> set[str]:
    words = re.findall(r"\b[a-zA-Z0-9_-]{3,}\b", text.lower())
    return {w for w in words if w not in _STOP_WORDS}


def is_near_duplicate_question(
    candidate: dict[str, Any], accepted_list: list[dict[str, Any]], threshold: float = 0.65
) -> tuple[bool, str]:
    """Detects if candidate question statement or options are near-duplicates of an accepted question.
    Computes Jaccard word-set similarity over non-stop tokens and checks option-set collision.
    """
    cand_tokens = _tokenize_meaningful(candidate.get("question_text", ""))
    if not cand_tokens:
        return False, "Empty token set"

    cand_options = set()
    if isinstance(candidate.get("options"), list):
        cand_options = {_normalize_answer(opt) for opt in candidate["options"]}

    for existing in accepted_list:
        exist_tokens = _tokenize_meaningful(existing.get("question_text", ""))
        if not exist_tokens:
            continue

        intersection = len(cand_tokens & exist_tokens)
        union = len(cand_tokens | exist_tokens)
        jaccard = intersection / union if union > 0 else 0.0

        if jaccard >= threshold:
            return True, f"High question lexical similarity (Jaccard {jaccard:.2f} >= {threshold})"

        if cand_options and isinstance(existing.get("options"), list):
            exist_options = {_normalize_answer(opt) for opt in existing["options"]}
            if len(cand_options & exist_options) >= max(3, len(cand_options) - 1):
                return True, "Colliding answer options with existing question"

    return False, "Unique"


def validate_chunk_grounding(
    q_data: dict[str, Any], chunk: Chunk | None, canonical_topic: str
) -> tuple[bool, str]:
    """Verifies that the generated question and correct answer have genuine textual grounding
    in the supporting chunk. Rejects questions whose answers or key concepts do not appear in the text.
    """
    if chunk is None:
        return False, "No supporting chunk provided for question."

    chunk_text = f"{chunk.topic or ''} {chunk.section_heading or ''} {chunk.text or ''} {chunk.contextual_prefix or ''}"
    chunk_tokens = _tokenize_meaningful(chunk_text)

    q_text = q_data.get("question_text", "")
    q_tokens = _tokenize_meaningful(q_text)

    topic_tokens = _tokenize_meaningful(canonical_topic)
    topic_in_q = bool(topic_tokens & q_tokens)
    topic_in_chunk = bool(topic_tokens & chunk_tokens)

    if not topic_in_q and not topic_in_chunk:
        return False, f"Question has no lexical connection to target topic '{canonical_topic}'."

    correct_ans = q_data.get("correct_answer")
    if correct_ans:
        if isinstance(correct_ans, list):
            ans_str = " ".join(correct_ans)
        elif str(correct_ans).startswith("["):
            try:
                ans_str = " ".join(json.loads(correct_ans))
            except Exception:
                ans_str = str(correct_ans)
        else:
            ans_str = str(correct_ans)

        ans_tokens = _tokenize_meaningful(ans_str)
        if q_data.get("question_type") != "true_false" and ans_tokens:
            grounded_tokens = ans_tokens & chunk_tokens
            if not grounded_tokens:
                expl_tokens = _tokenize_meaningful(q_data.get("explanation") or "")
                if not (ans_tokens & expl_tokens):
                    return False, f"Correct answer '{ans_str}' is not supported by cited source chunk."

    question_overlap = q_tokens & chunk_tokens
    if len(question_overlap) < 1 and len(q_tokens) >= 3:
        return False, "Question text has insufficient factual overlap with supporting chunk."

    return True, "Valid"


def _find_best_supporting_chunk(
    q_text: str, expl: str | None, chunks_with_sim: list[tuple[Chunk, float]]
) -> Chunk:
    """Finds the chunk with highest lexical overlap for accurate provenance attribution."""
    if not chunks_with_sim:
        return None
    words = set(re.findall(r"\w+", f"{q_text} {expl or ''}".lower()))
    best_chunk = chunks_with_sim[0][0]
    best_overlap = -1
    for c, _ in chunks_with_sim:
        c_words = set(re.findall(r"\w+", (c.text or "").lower()))
        overlap = len(words & c_words)
        if overlap > best_overlap:
            best_overlap = overlap
            best_chunk = c
    return best_chunk


def retrieve_topic_grounded_chunks(
    db: Session,
    class_id: uuid.UUID,
    subject: str | None,
    subject_id: str | None,
    canonical_topic: str,
    topic_row: PrerequisiteMap | None,
    embedding_model: Any,
    top_k: int = 6,
) -> list[tuple[Chunk, float]]:
    """Retrieves curriculum chunks strictly scoped to the class with multi-stage topic prioritization:
    1. Direct canonical topic/document match (Chunk.topic matching canonical topic or topic's source_document).
    2. Vector cosine distance on enriched topic anchor (topic name + description + subtopics + objectives).
    3. Structured lexical match across ready chunks in the class.
    Filters out chunks with cosine distance that indicates irrelevance (< 0.20 similarity).
    """
    retrieved_map: dict[uuid.UUID, tuple[Chunk, float]] = {}

    subtopics = [s.name for s in topic_row.subtopics] if topic_row and hasattr(topic_row, "subtopics") and topic_row.subtopics else []
    objectives = [getattr(o, "statement", getattr(o, "objective", "")) for o in topic_row.learning_objectives] if topic_row and hasattr(topic_row, "learning_objectives") and topic_row.learning_objectives else []
    unit = topic_row.unit if topic_row else None
    source_doc_id = topic_row.source_document_id if topic_row else None

    # Priority 1: Chunks explicitly tagged with the topic in this class or from the topic's source document
    base_q = (
        db.query(Chunk)
        .join(Document, Chunk.document_id == Document.id)
        .filter(Document.class_id == class_id, Document.deleted == False)  # noqa: E712
    )

    if source_doc_id:
        doc_chunks = (
            base_q.filter(Chunk.document_id == source_doc_id)
            .order_by(Chunk.chunk_index)
            .limit(top_k)
            .all()
        )
        for c in doc_chunks:
            retrieved_map[c.id] = (c, 0.95)

    if len(retrieved_map) < top_k:
        topic_chunks = base_q.filter(Chunk.topic.ilike(f"%{canonical_topic}%")).limit(top_k).all()
        for c in topic_chunks:
            if c.id not in retrieved_map:
                retrieved_map[c.id] = (c, 0.90)

    # Priority 2: Vector retrieval with enriched semantic query
    if len(retrieved_map) < top_k and embedding_model:
        from backend.pipeline.embedder import embed_single

        anchor_components = [canonical_topic]
        if topic_row and topic_row.description:
            anchor_components.append(topic_row.description)
        if subtopics:
            anchor_components.append("Subtopics: " + ", ".join(subtopics))
        if objectives:
            anchor_components.append("Objectives: " + ", ".join(objectives))

        enriched_query = ". ".join(anchor_components)
        try:
            query_vector = embed_single(enriched_query, model=embedding_model)
            vector_results = rag_service.retrieve_chunks(
                db,
                subject,
                query_vector,
                top_k=top_k,
                subject_id=subject_id,
                class_id=str(class_id),
            )
            for c, sim in vector_results:
                if sim >= 0.20 and c.id not in retrieved_map:
                    retrieved_map[c.id] = (c, float(sim))
        except Exception as exc:
            print(f"[TOPIC CHUNKS] Vector retrieval failed ({exc}), falling back to lexical search.")

    # Priority 3: Structured lexical fallback
    if len(retrieved_map) < top_k:
        lex_candidates = (
            base_q.filter(
                (Chunk.section_heading.ilike(f"%{canonical_topic}%"))
                | (Chunk.text.ilike(f"%{canonical_topic}%"))
                | (Chunk.full_text.ilike(f"%{canonical_topic}%"))
            )
            .limit(top_k)
            .all()
        )
        for c in lex_candidates:
            if c.id not in retrieved_map:
                retrieved_map[c.id] = (c, 0.75)

    # Priority 4: Unit-scoped fallback if topic is in a specific unit
    if len(retrieved_map) < top_k and unit is not None:
        unit_candidates = base_q.filter(Chunk.unit == unit).limit(top_k).all()
        for c in unit_candidates:
            if c.id not in retrieved_map:
                retrieved_map[c.id] = (c, 0.60)

    # Sort descending by relevance score
    sorted_chunks = sorted(retrieved_map.values(), key=lambda pair: pair[1], reverse=True)[:top_k]
    return sorted_chunks


def _extract_json_array(text: str) -> list[dict[str, Any]]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"Could not parse JSON array from LLM output: {text[:200]!r}")


def _normalize_answer(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(str(value).split()).casefold()


def _validate_generated_question(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    try:
        question_text = item["question"]
        options = item["options"]
        correct_answer = item["correct_answer"]
        raw_difficulty = item.get("difficulty")
    except KeyError:
        return None

    if not isinstance(question_text, str) or not question_text.strip():
        return None

    if not isinstance(options, list) or len(options) != 4:
        return None

    for opt in options:
        if not isinstance(opt, str) or not opt.strip():
            return None

    normalized_options = [_normalize_answer(opt) for opt in options]
    if len(set(normalized_options)) != 4:
        return None

    if not isinstance(correct_answer, str) or not correct_answer.strip():
        return None

    if correct_answer not in options:
        return None

    if isinstance(raw_difficulty, str) and raw_difficulty.strip().lower() in {"easy", "medium", "hard"}:
        difficulty = raw_difficulty.strip().lower()
    else:
        difficulty = "medium"

    return {
        "question": question_text,
        "options": options,
        "correct_answer": correct_answer,
        "difficulty": difficulty,
    }


SUPPORTED_QUESTION_TYPES = {"single_choice", "multiple_choice", "true_false"}


def validate_and_normalize_question_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Validates question payload against Phase 3 question types (single_choice, multiple_choice, true_false).

    Enforces option uniqueness, valid answer mappings, and point configurations.
    """
    question_text = str(data.get("question_text") or "").strip()
    if not question_text:
        raise ValueError("Question text cannot be empty.")

    raw_q_type = data.get("question_type") or "single_choice"
    if hasattr(raw_q_type, "value"):
        raw_q_type = raw_q_type.value
    raw_q_type = str(raw_q_type).lower().strip()

    if raw_q_type not in SUPPORTED_QUESTION_TYPES:
        raise ValueError(
            f"Unsupported question type '{raw_q_type}'. "
            f"Allowed question types in Phase 3 are: single_choice, multiple_choice, true_false."
        )

    raw_options = data.get("options")
    if not isinstance(raw_options, (list, tuple)):
        raise ValueError("Options must be a list of non-empty strings.")

    options = [str(opt).strip() for opt in raw_options if opt is not None and str(opt).strip()]
    if raw_q_type in ("single_choice", "multiple_choice") and len(options) < 2:
        raise ValueError(f"{raw_q_type.replace('_', ' ').title()} questions require at least 2 distinct options.")

    # Check for duplicate options (case-insensitive collision check)
    norm_opts = [_normalize_answer(opt) for opt in options]
    if len(set(norm_opts)) != len(options):
        raise ValueError("Duplicate options are not allowed (case-insensitive collision).")

    raw_correct = data.get("correct_answer")
    if raw_correct is None or (isinstance(raw_correct, str) and not raw_correct.strip()) or (isinstance(raw_correct, (list, tuple)) and not raw_correct):
        raise ValueError("Correct answer is required.")

    partial_credit = bool(data.get("partial_credit_allowed", False))

    if raw_q_type == "single_choice":
        correct_str = str(raw_correct).strip()
        matching_opt = next((opt for opt in options if _normalize_answer(opt) == _normalize_answer(correct_str)), None)
        if not matching_opt:
            raise ValueError(f"Correct answer '{correct_str}' does not match any of the provided options: {options}")
        normalized_correct = matching_opt
        partial_credit = False

    elif raw_q_type == "true_false":
        standard_tf = ["True", "False"]
        options = standard_tf
        correct_val = str(raw_correct).strip().capitalize()
        if correct_val not in ("True", "False"):
            raise ValueError(f"True/False questions require correct_answer to be 'True' or 'False', got: '{raw_correct}'")
        normalized_correct = correct_val
        partial_credit = False

    elif raw_q_type == "multiple_choice":
        # Extract list of correct choices
        if isinstance(raw_correct, (list, tuple)):
            correct_items = [str(c).strip() for c in raw_correct if str(c).strip()]
        elif isinstance(raw_correct, str):
            if raw_correct.strip().startswith("["):
                try:
                    correct_items = [str(c).strip() for c in json.loads(raw_correct) if str(c).strip()]
                except Exception:
                    correct_items = [c.strip() for c in raw_correct.split(",") if c.strip()]
            else:
                correct_items = [c.strip() for c in raw_correct.split(",") if c.strip()]
        else:
            correct_items = [str(raw_correct).strip()]

        if not correct_items:
            raise ValueError("Multiple-choice questions require at least one correct answer option.")

        # Every correct option must match one of the available options
        matched_correct = []
        for item in correct_items:
            found = next((opt for opt in options if _normalize_answer(opt) == _normalize_answer(item)), None)
            if not found:
                raise ValueError(f"Correct answer item '{item}' does not match any of the provided options: {options}")
            if found not in matched_correct:
                matched_correct.append(found)

        normalized_correct = json.dumps(matched_correct)

    points = float(data.get("points", 1.0))
    if points <= 0:
        raise ValueError("Question points must be greater than 0.")

    difficulty = data.get("difficulty", "medium")
    if hasattr(difficulty, "value"):
        difficulty = difficulty.value
    difficulty = str(difficulty).lower().strip()
    if difficulty not in {"easy", "medium", "hard"}:
        difficulty = "medium"

    return {
        "question_text": question_text,
        "options": options,
        "correct_answer": normalized_correct,
        "question_type": raw_q_type,
        "points": points,
        "difficulty": difficulty,
        "partial_credit_allowed": partial_credit,
        "explanation": str(data.get("explanation") or "").strip() or None,
    }


def create_manual_quiz(
    db: Session,
    class_id: str,
    title: str,
    created_by_id: Any,
    description: str | None = None,
    unit: int | None = None,
    chapter: int | None = None,
    document_id: str | None = None,
    time_limit_minutes: int | None = None,
    passing_percentage: float = 60.0,
    status: ReviewStatus = ReviewStatus.draft,
) -> Quiz:
    """Creates a new manual or draft quiz for a class."""
    quiz = Quiz(
        title=title.strip(),
        description=description.strip() if description else None,
        unit=unit,
        chapter=chapter,
        generation_type="manual",
        status=status,
        version=1,
        time_limit_minutes=time_limit_minutes,
        passing_percentage=passing_percentage,
        class_id=uuid.UUID(str(class_id)),
        document_id=uuid.UUID(str(document_id)) if document_id else None,
        created_by_id=uuid.UUID(str(created_by_id)) if created_by_id else None,
    )
    db.add(quiz)
    db.commit()
    db.refresh(quiz)
    print(f"[QUIZ AUTHORING] Created draft quiz {quiz.id} '{quiz.title}' (class={class_id})")
    return quiz


def create_question(
    db: Session,
    quiz: Quiz,
    data: dict[str, Any],
) -> QuizQuestion:
    """Creates a question in a quiz, handles ordering, provenance, and curriculum mapping."""
    validated = validate_and_normalize_question_payload(data)

    # Determine order
    order = data.get("question_order")
    if order is None or int(order) <= 0:
        max_order = max([q.question_order for q in quiz.questions], default=0)
        order = max_order + 1
    else:
        order = int(order)

    # Bump version if student attempts exist for this quiz
    has_attempts = db.query(QuizAttempt).filter(QuizAttempt.quiz_id == quiz.id).count() > 0
    if has_attempts:
        quiz.version += 1
        quiz.updated_at = datetime.now(timezone.utc)

    # Curriculum mapping association
    topic_id = data.get("topic_id")
    topic_name = data.get("topic")
    if topic_id:
        topic_row = db.get(PrerequisiteMap, uuid.UUID(str(topic_id)))
        if topic_row:
            topic_name = topic_row.topic
            topic_id = topic_row.id
        else:
            raise ValueError(f"Topic ID '{topic_id}' not found in curriculum prerequisite map.")
    elif topic_name and str(topic_name).strip() and quiz.class_id:
        class_row = db.get(Class, quiz.class_id)
        if class_row and class_row.subject_id:
            found = db.query(PrerequisiteMap).filter(
                PrerequisiteMap.subject_id == class_row.subject_id,
                PrerequisiteMap.topic.ilike(str(topic_name).strip()),
            ).first()
            if found:
                topic_id = found.id
                topic_name = found.topic

    # Source document verification
    source_doc_id = data.get("source_document_id")
    if source_doc_id:
        doc_row = db.get(Document, uuid.UUID(str(source_doc_id)))
        if not doc_row:
            raise ValueError(f"Source document ID '{source_doc_id}' not found.")
        source_doc_id = doc_row.id

    question = QuizQuestion(
        quiz_id=quiz.id,
        question_text=validated["question_text"],
        options=json.dumps(validated["options"]),
        correct_answer=validated["correct_answer"],
        question_type=validated["question_type"],
        question_order=order,
        explanation=validated["explanation"],
        points=validated["points"],
        partial_credit_allowed=validated["partial_credit_allowed"],
        difficulty=QuestionDifficulty(validated["difficulty"]),
        status=ReviewStatus.approved if quiz.status == ReviewStatus.approved else ReviewStatus.pending_review,
        topic=topic_name,
        topic_id=topic_id,
        source_document_id=source_doc_id,
        source_page_number=data.get("source_page_number"),
        version=quiz.version,
    )
    db.add(question)
    db.flush()

    # Detailed subtopic / learning objective mapping
    subtopic_id = data.get("subtopic_id")
    objective_id = data.get("objective_id")
    if subtopic_id or objective_id:
        sub_uuid = None
        obj_uuid = None
        bloom = data.get("bloom_level")

        if subtopic_id:
            sub = db.get(SyllabusSubtopic, uuid.UUID(str(subtopic_id)))
            if not sub:
                raise ValueError(f"Subtopic ID '{subtopic_id}' not found.")
            sub_uuid = sub.id

        if objective_id:
            obj = db.get(LearningObjective, uuid.UUID(str(objective_id)))
            if not obj:
                raise ValueError(f"Learning Objective ID '{objective_id}' not found.")
            obj_uuid = obj.id
            if not bloom and obj.bloom_level:
                bloom = obj.bloom_level

        mapping = QuestionCurriculumMapping(
            question_id=question.id,
            topic_id=topic_id,
            subtopic_id=sub_uuid,
            objective_id=obj_uuid,
            bloom_level=bloom,
        )
        db.add(mapping)

    quiz.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(question)
    return question


def update_question(
    db: Session,
    question: QuizQuestion,
    updates: dict[str, Any],
) -> QuizQuestion:
    """Updates question fields, bumps quiz version if attempts exist, and updates curriculum links."""
    quiz = question.quiz
    has_attempts = db.query(QuizAttempt).filter(QuizAttempt.quiz_id == quiz.id).count() > 0
    if has_attempts:
        quiz.version += 1
        quiz.updated_at = datetime.now(timezone.utc)
        question.version = quiz.version

    existing_options = json.loads(question.options) if question.options else []
    new_data = {
        "question_text": updates.get("question_text", question.question_text),
        "options": updates.get("options", existing_options),
        "correct_answer": updates.get("correct_answer", question.correct_answer),
        "question_type": updates.get("question_type", question.question_type),
        "points": updates.get("points", question.points),
        "difficulty": updates.get("difficulty", question.difficulty),
        "partial_credit_allowed": updates.get("partial_credit_allowed", question.partial_credit_allowed),
        "explanation": updates.get("explanation", question.explanation),
    }
    validated = validate_and_normalize_question_payload(new_data)

    question.question_text = validated["question_text"]
    question.options = json.dumps(validated["options"])
    question.correct_answer = validated["correct_answer"]
    question.question_type = validated["question_type"]
    question.points = validated["points"]
    question.difficulty = QuestionDifficulty(validated["difficulty"])
    question.partial_credit_allowed = validated["partial_credit_allowed"]
    question.explanation = validated["explanation"]

    if "question_order" in updates and updates["question_order"] is not None:
        question.question_order = int(updates["question_order"])

    if "topic_id" in updates:
        tid = updates["topic_id"]
        if tid:
            topic_row = db.get(PrerequisiteMap, uuid.UUID(str(tid)))
            if not topic_row:
                raise ValueError(f"Topic ID '{tid}' not found.")
            question.topic_id = topic_row.id
            question.topic = topic_row.topic
        else:
            question.topic_id = None
            if "topic" in updates:
                question.topic = updates["topic"]

    elif "topic" in updates and updates["topic"] is not None:
        question.topic = updates["topic"]

    if "source_document_id" in updates:
        s_doc = updates["source_document_id"]
        if s_doc:
            doc_row = db.get(Document, uuid.UUID(str(s_doc)))
            if not doc_row:
                raise ValueError(f"Source document ID '{s_doc}' not found.")
            question.source_document_id = doc_row.id
        else:
            question.source_document_id = None

    if "source_page_number" in updates:
        question.source_page_number = updates["source_page_number"]

    if "status" in updates and updates["status"]:
        st = updates["status"]
        if hasattr(st, "value"):
            st = st.value
        question.status = ReviewStatus(st)

    # Update or add curriculum mapping
    subtopic_id = updates.get("subtopic_id")
    objective_id = updates.get("objective_id")
    if subtopic_id or objective_id:
        mapping = (
            db.query(QuestionCurriculumMapping)
            .filter(QuestionCurriculumMapping.question_id == question.id)
            .first()
        )
        if not mapping:
            mapping = QuestionCurriculumMapping(question_id=question.id)
            db.add(mapping)
        if subtopic_id:
            sub = db.get(SyllabusSubtopic, uuid.UUID(str(subtopic_id)))
            if not sub:
                raise ValueError(f"Subtopic ID '{subtopic_id}' not found.")
            mapping.subtopic_id = sub.id
        if objective_id:
            obj = db.get(LearningObjective, uuid.UUID(str(objective_id)))
            if not obj:
                raise ValueError(f"Learning Objective ID '{objective_id}' not found.")
            mapping.objective_id = obj.id
        mapping.topic_id = question.topic_id

    question.updated_at = datetime.utcnow()
    quiz.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(question)
    return question


def reorder_questions(db: Session, quiz: Quiz, question_ids: list[Any]) -> list[QuizQuestion]:
    """Reorders questions deterministically using a list of question UUIDs."""
    existing_map = {q.id: q for q in quiz.questions}
    target_uuids = [uuid.UUID(str(qid)) for qid in question_ids]

    if set(target_uuids) != set(existing_map.keys()):
        raise ValueError("Reorder list must contain exactly the question IDs belonging to this quiz.")

    for new_order, qid in enumerate(target_uuids, start=1):
        existing_map[qid].question_order = new_order

    quiz.updated_at = datetime.now(timezone.utc)
    db.commit()
    return sorted(quiz.questions, key=lambda q: q.question_order)


def delete_question(db: Session, question: QuizQuestion) -> None:
    """Safely deletes question if no student attempts reference it."""
    answers_count = db.query(QuizAttemptAnswer).filter(QuizAttemptAnswer.question_id == question.id).count()
    if answers_count > 0:
        raise ValueError(
            "Cannot delete question because student attempt answers are recorded against it. "
            "Archive or deactivate the question instead to preserve assessment records."
        )

    quiz = question.quiz
    db.delete(question)
    quiz.updated_at = datetime.now(timezone.utc)
    db.commit()


def delete_quiz(db: Session, quiz: Quiz) -> None:
    """Safely deletes quiz if no student attempts exist."""
    attempts_count = db.query(QuizAttempt).filter(QuizAttempt.quiz_id == quiz.id).count()
    if attempts_count > 0:
        raise ValueError(
            "Cannot delete quiz because student attempts exist for it. "
            "Archive the quiz instead to preserve historical assessment records."
        )
    db.delete(quiz)
    db.commit()


def publish_quiz(db: Session, quiz: Quiz) -> Quiz:
    """Publishes a quiz, approving its questions and making it available to enrolled students."""
    if not quiz.questions:
        raise ValueError("Cannot publish an empty quiz. Add at least one question first.")

    approved_count = 0
    for q in quiz.questions:
        if q.status != ReviewStatus.rejected:
            q.status = ReviewStatus.approved
            approved_count += 1

    if approved_count == 0:
        raise ValueError("Quiz has no valid questions to publish.")

    quiz.status = ReviewStatus.approved
    quiz.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(quiz)
    print(f"[QUIZ PUBLISH] Quiz {quiz.id} published with {approved_count} approved questions (version {quiz.version})")
    return quiz


def archive_quiz(db: Session, quiz: Quiz) -> Quiz:
    """Archives a quiz, removing it from student discovery while preserving attempts."""
    quiz.status = ReviewStatus.archived
    quiz.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(quiz)
    print(f"[QUIZ ARCHIVE] Quiz {quiz.id} archived.")
    return quiz


def calibrate_bloom_level(raw_bloom: str | None, question_text: str, difficulty: str) -> str:
    raw = str(raw_bloom or "").strip().lower()
    if raw in {"remember", "understand", "apply", "analyze"}:
        return raw
    q_lower = (question_text or "").lower()
    if any(kw in q_lower for kw in ["compare", "differentiate", "analyze", "why does", "break down"]):
        return "analyze"
    elif any(kw in q_lower for kw in ["apply", "scenario", "calculate", "if a student", "given that"]):
        return "apply"
    elif any(kw in q_lower for kw in ["explain", "describe", "interpret", "meaning"]):
        return "understand"
    elif str(difficulty).lower() == "hard":
        return "analyze"
    elif str(difficulty).lower() == "medium":
        return "apply"
    else:
        return "remember"


def load_existing_question_payloads(db: Session, class_id: str, limit: int = 200) -> list[dict[str, Any]]:
    try:
        class_uuid = uuid.UUID(str(class_id))
    except Exception:
        return []
    try:
        rows = (
            db.query(QuizQuestion.question_text, QuizQuestion.options)
            .join(Quiz, QuizQuestion.quiz_id == Quiz.id)
            .filter(
                Quiz.class_id == class_uuid,
                or_(Quiz.generation_type.is_(None), Quiz.generation_type != "topic_practice"),
                QuizQuestion.status != ReviewStatus.rejected,
            )
            .order_by(QuizQuestion.updated_at.desc())
            .limit(limit)
            .all()
        )
        payloads = []
        for q_text, q_opts in rows:
            opts_list = []
            if q_opts:
                try:
                    loaded = json.loads(q_opts)
                    if isinstance(loaded, list):
                        opts_list = [str(x) for x in loaded]
                    elif loaded is not None:
                        opts_list = [str(loaded)]
                except Exception:
                    opts_list = [str(q_opts)]
            payloads.append({
                "question_text": q_text or "",
                "options": opts_list,
            })
        return payloads
    except Exception as exc:
        logger.warning("Failed loading existing question payloads for class %s: %s", class_id, exc)
        return []


def load_used_chunk_ids(db: Session, class_id: str, chapter: int) -> set[uuid.UUID]:
    try:
        class_uuid = uuid.UUID(str(class_id))
        rows = (
            db.query(QuizQuestion.source_chunk_id)
            .join(Quiz, QuizQuestion.quiz_id == Quiz.id)
            .filter(
                Quiz.class_id == class_uuid,
                Quiz.chapter == chapter,
                or_(Quiz.generation_type.is_(None), Quiz.generation_type != "topic_practice"),
                QuizQuestion.status != ReviewStatus.rejected,
                QuizQuestion.source_chunk_id.isnot(None),
            )
            .distinct()
            .all()
        )
        return {r[0] for r in rows if r[0] is not None}
    except Exception as exc:
        logger.warning("Failed loading used chunk ids for class %s chapter %s: %s", class_id, chapter, exc)
        return set()


def build_avoid_block(existing_texts: list[str], max_items: int = 15) -> str:
    if not existing_texts:
        return ""
    cleaned = [t.strip()[:160] for t in existing_texts if t and t.strip()]
    if not cleaned:
        return ""
    selected = cleaned[:max_items]
    lines = [f"- {t}" for t in selected]
    return "Existing questions - do not repeat these concepts or wording:\n" + "\n".join(lines) + "\n\n"


def resolve_question_topic(
    db: Session,
    subject_id: str | None,
    subject: str | None,
    chunk: Chunk | None,
    question_text: str,
    embedding_model: Any,
) -> tuple[str | None, uuid.UUID | None]:
    try:
        subj_uuid = uuid.UUID(str(subject_id)) if subject_id else None

        # (1) PrerequisiteMap row with same subject_id whose topic equals chunk.topic (case-insensitive)
        if chunk and chunk.topic and subj_uuid:
            chunk_topic_norm = chunk.topic.strip().lower()
            topic_row = (
                db.query(PrerequisiteMap)
                .filter(
                    PrerequisiteMap.subject_id == subj_uuid,
                    func.lower(PrerequisiteMap.topic) == chunk_topic_norm,
                )
                .first()
            )
            if topic_row:
                return topic_row.topic, topic_row.id

        # (2) Existing topic detection used by generate_quiz today
        detected_name = None
        if subject_id:
            detected_name = context_service.detect_topic_for_subject(
                db, question_text, str(subject_id), embedding_model
            )
        else:
            detected_name = context_service.detect_topic(question_text, subject or "")

        if detected_name:
            det_norm = detected_name.strip().lower()
            query = db.query(PrerequisiteMap).filter(func.lower(PrerequisiteMap.topic) == det_norm)
            if subj_uuid:
                query = query.filter(PrerequisiteMap.subject_id == subj_uuid)
            matched_row = query.first()
            if matched_row:
                return matched_row.topic, matched_row.id
            return detected_name, None

        # (3) Fall back to chunk.topic or None
        if chunk and chunk.topic:
            return chunk.topic, None
        return None, None
    except Exception as exc:
        logger.warning("Error in resolve_question_topic: %s", exc)
        return (chunk.topic if chunk else None), None


def match_objective_and_subtopic(
    db: Session,
    topic_id: uuid.UUID | str,
    question_text: str,
    explanation: str | None = None,
) -> tuple[uuid.UUID | None, uuid.UUID | None, str | None]:
    """Matches a generated question against SyllabusSubtopic and LearningObjective rows.
    Returns: (subtopic_id | None, objective_id | None, objective_bloom | None)
    Never raises; returns (None, None, None) on any failure.
    """
    try:
        t_uuid = uuid.UUID(str(topic_id)) if not isinstance(topic_id, uuid.UUID) else topic_id
        text_for_tokens = f"{question_text} {explanation or ''}"
        cand_tokens = _tokenize_meaningful(text_for_tokens)
        if not cand_tokens:
            return None, None, None

        # 1. Check LearningObjective rows for this topic
        objectives = (
            db.query(LearningObjective)
            .filter(
                LearningObjective.topic_id == t_uuid,
                or_(
                    LearningObjective.review_status == "approved",
                    LearningObjective.review_status.is_(None),
                ),
            )
            .all()
        )
        best_obj = None
        best_obj_score = 0.0
        best_obj_shared = 0

        for obj in objectives:
            statement = obj.statement or ""
            obj_tokens = _tokenize_meaningful(statement)
            if not obj_tokens:
                continue
            shared = cand_tokens & obj_tokens
            shared_cnt = len(shared)
            score = shared_cnt / len(obj_tokens)
            if shared_cnt >= 2 and score >= 0.25:
                if (score > best_obj_score) or (score == best_obj_score and shared_cnt > best_obj_shared):
                    best_obj = obj
                    best_obj_score = score
                    best_obj_shared = shared_cnt

        if best_obj:
            return best_obj.subtopic_id, best_obj.id, best_obj.bloom_level

        # 2. If no objective qualifies, score subtopics against their names
        subtopics = (
            db.query(SyllabusSubtopic)
            .filter(
                SyllabusSubtopic.topic_id == t_uuid,
                or_(
                    SyllabusSubtopic.review_status == "approved",
                    SyllabusSubtopic.review_status.is_(None),
                ),
            )
            .all()
        )
        best_sub = None
        best_sub_score = 0.0
        best_sub_shared = 0

        for sub in subtopics:
            name = sub.name or ""
            sub_tokens = _tokenize_meaningful(name)
            if not sub_tokens:
                continue
            shared = cand_tokens & sub_tokens
            shared_cnt = len(shared)
            score = shared_cnt / len(sub_tokens)
            if shared_cnt >= 1 and score >= 0.34:
                if (score > best_sub_score) or (score == best_sub_score and shared_cnt > best_sub_shared):
                    best_sub = sub
                    best_sub_score = score
                    best_sub_shared = shared_cnt

        if best_sub:
            return best_sub.id, None, None

        return None, None, None
    except Exception as exc:
        logger.warning("match_objective_and_subtopic failed: %s", exc)
        return None, None, None


async def generate_quiz(
    db: Session,
    class_id: str,
    document_id: str | None,
    unit: int,
    chapter: int,
    title: str,
    created_by_id: str,
    embedding_model: Any,
    num_questions: int = 10,
) -> Quiz:
    logger.info("Starting standard quiz generation: class=%s unit=%d chapter=%d n=%d", class_id, unit, chapter, num_questions)

    class_row = db.get(Class, class_id)
    if class_row is None:
        raise ValueError(f"Class '{class_id}' not found.")
    subject = class_row.subject
    subject_id = str(class_row.subject_id) if class_row.subject_id else None
    if not subject and not subject_id:
        raise ValueError(
            f"Class '{class_id}' has no subject set. Assign a subject to the class before generating quizzes."
        )

    from backend.pipeline.embedder import embed_single

    seed_vector = embed_single(f"{subject or 'curriculum'} chapter {chapter}", model=embedding_model)
    chunks_with_sim = rag_service.retrieve_chunks(
        db, subject, seed_vector, top_k=12, chapter_scope=[chapter], subject_id=subject_id, class_id=class_id
    )

    if not chunks_with_sim:
        raise ValueError(f"No curriculum content found for subject={subject} chapter={chapter} — upload a document first.")

    # Reorder so chunks NOT in load_used_chunk_ids come first (keep similarity order inside each group); take first 6
    used_chunk_ids = load_used_chunk_ids(db, class_id, chapter)
    unused_chunks = [pair for pair in chunks_with_sim if pair[0].id not in used_chunk_ids]
    used_chunks = [pair for pair in chunks_with_sim if pair[0].id in used_chunk_ids]
    chunks_with_sim = (unused_chunks + used_chunks)[:6]

    # Build numbered '[Source N] (Section: ...) (Page ...)' blocks
    source_blocks = []
    for idx, (chunk, _sim) in enumerate(chunks_with_sim, start=1):
        heading = f" (Section: {chunk.section_heading})" if chunk.section_heading else ""
        page = f" (Page {chunk.page_number})" if chunk.page_number else ""
        source_blocks.append(f"[Source {idx}]{heading}{page}\n{chunk.text}")
    content = "\n\n".join(source_blocks)[:6000]

    # Existing question payloads for duplicate checking and avoid block
    existing_payloads = load_existing_question_payloads(db, class_id, limit=200)
    try:
        class_uuid = uuid.UUID(str(class_id))
        same_chapter_q = (
            db.query(QuizQuestion.question_text)
            .join(Quiz, QuizQuestion.quiz_id == Quiz.id)
            .filter(
                Quiz.class_id == class_uuid,
                Quiz.chapter == chapter,
                or_(Quiz.generation_type.is_(None), Quiz.generation_type != "topic_practice"),
                QuizQuestion.status != ReviewStatus.rejected,
            )
            .order_by(QuizQuestion.updated_at.desc())
            .limit(30)
            .all()
        )
        same_chapter_texts = [r[0] for r in same_chapter_q if r[0]]
    except Exception:
        same_chapter_texts = []

    all_existing_texts = same_chapter_texts + [
        p["question_text"] for p in existing_payloads if p["question_text"] not in same_chapter_texts
    ]
    avoid_block = build_avoid_block(all_existing_texts, max_items=15)

    request_candidates_count = max(num_questions + 3, int(num_questions * 1.5))
    prompt = QUIZ_GENERATION_PROMPT_V2.format(
        n=request_candidates_count,
        content=content,
        avoid_block=avoid_block,
    )

    provider, model_idx = rag_service.get_llm_provider()
    logger.info("Calling LLM for standard quiz (%d requested candidates)...", request_candidates_count)

    raw_output = None
    parsed: list[dict[str, Any]] | None = None
    for attempt in range(2):
        raw_output = await provider.generate(prompt, max_tokens=3000)
        try:
            parsed = _extract_json_array(raw_output)
            break
        except (ValueError, json.JSONDecodeError) as e:
            logger.warning("Attempt %d produced unparseable JSON: %s", attempt + 1, e)
            prompt = prompt + "\n\nIMPORTANT: respond with ONLY the JSON array, no preamble, no markdown."

    if parsed is None or not isinstance(parsed, list):
        raise ValueError(
            f"LLM failed to produce valid JSON after retries. Last output: {raw_output[:300] if raw_output else 'none'}"
        )

    from backend.llm.model_pool import model_pool

    tokens_used = rag_service.estimate_tokens(prompt) + rag_service.estimate_tokens(raw_output or "")
    model_pool.record_usage(model_idx, tokens_used)
    logger.info("Parsed %d candidate questions, ~%d tokens used", len(parsed), tokens_used)

    accepted_pairs: list[tuple[dict[str, Any], Chunk, str, str | None, uuid.UUID | None]] = []
    accepted_payloads: list[dict[str, Any]] = []
    rejection_counts: dict[str, int] = {}
    distinct_reasons: list[str] = []

    for item in parsed:
        if not isinstance(item, dict):
            continue
        raw_q_text = str(item.get("question_text") or item.get("question") or "").strip()
        payload_dict = {
            "question_text": raw_q_text,
            "options": item.get("options"),
            "correct_answer": item.get("correct_answer"),
            "question_type": item.get("question_type") or "single_choice",
            "difficulty": item.get("difficulty") or "medium",
            "explanation": item.get("explanation"),
            "points": 1.0,
            "partial_credit_allowed": (item.get("question_type") == "multiple_choice"),
        }

        # 1. Schema validation
        try:
            validated = validate_and_normalize_question_payload(payload_dict)
        except ValueError as exc:
            reason = f"Schema: {exc}"
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            if reason not in distinct_reasons:
                distinct_reasons.append(reason)
            continue

        # 2. Duplicate check against existing payloads + accepted ones
        is_dup, dup_reason = is_near_duplicate_question(validated, existing_payloads + accepted_payloads)
        if is_dup:
            reason = f"Duplicate: {dup_reason}"
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            if reason not in distinct_reasons:
                distinct_reasons.append(reason)
            continue

        # 3. Supporting chunk selection
        assigned_chunk: Chunk | None = None
        c_idx = item.get("chunk_index")
        if isinstance(c_idx, int) and 1 <= c_idx <= len(chunks_with_sim):
            candidate_chunk = chunks_with_sim[c_idx - 1][0]
            assigned_chunk = candidate_chunk

        if not assigned_chunk:
            assigned_chunk = _find_best_supporting_chunk(
                validated["question_text"], validated.get("explanation") or "", chunks_with_sim
            )

        # 4. Resolve topic
        topic_name, topic_id = resolve_question_topic(
            db, subject_id, subject, assigned_chunk, validated["question_text"], embedding_model
        )

        # 5. Chunk grounding validation
        grounding_topic = topic_name or (assigned_chunk.topic if assigned_chunk else None) or subject or "Curriculum"
        is_grounded, ground_reason = validate_chunk_grounding(validated, assigned_chunk, grounding_topic)
        if not is_grounded:
            reason = f"Grounding: {ground_reason}"
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            if reason not in distinct_reasons:
                distinct_reasons.append(reason)
            continue

        # 6. Bloom level
        bloom_level = calibrate_bloom_level(
            item.get("bloom_level"), validated["question_text"], validated["difficulty"]
        )
        validated["chunk_index"] = item.get("chunk_index")

        accepted_pairs.append((validated, assigned_chunk, bloom_level, topic_name, topic_id))
        accepted_payloads.append(validated)
        if len(accepted_pairs) >= num_questions:
            break

    total_rejected = sum(rejection_counts.values())
    logger.info(
        "generate_quiz results: requested=%d candidates=%d accepted=%d rejected=%d breakdown=%s",
        num_questions, len(parsed), len(accepted_pairs), total_rejected, rejection_counts,
    )

    if not accepted_pairs:
        top_reasons = "; ".join(distinct_reasons[:3])
        raise ValueError(
            f"No valid questions could be generated from the curriculum content. "
            f"Candidates evaluated: {len(parsed)}. Failure details: {top_reasons}"
        )

    try:
        quiz = Quiz(
            title=title,
            unit=unit,
            chapter=chapter,
            generation_type="standard",
            status=ReviewStatus.pending_review,
            class_id=class_id,
            document_id=document_id,
            created_by_id=created_by_id,
        )
        db.add(quiz)
        db.flush()

        for idx, (q_data, chunk, bloom, t_name, t_id) in enumerate(accepted_pairs, start=1):
            subtopic_id = None
            objective_id = None
            effective_bloom = bloom
            if t_id:
                subtopic_id, objective_id, obj_bloom = match_objective_and_subtopic(
                    db, t_id, q_data["question_text"], q_data.get("explanation")
                )
                if not effective_bloom and obj_bloom:
                    effective_bloom = obj_bloom

            raw_chunk_idx = q_data.get("chunk_index")
            valid_chunk_idx = None
            if isinstance(raw_chunk_idx, int) and raw_chunk_idx > 0:
                valid_chunk_idx = raw_chunk_idx
            elif isinstance(raw_chunk_idx, str) and raw_chunk_idx.isdigit() and int(raw_chunk_idx) > 0:
                valid_chunk_idx = int(raw_chunk_idx)

            provenance_dict = {
                "generator": "standard",
                "prompt_version": "v2",
                "model_index": model_idx,
                "bloom_level": effective_bloom,
                "chunk_index": valid_chunk_idx,
                "validation": {
                    "schema": True,
                    "duplicate_check": True,
                    "grounding": True,
                },
                "batch_requested": num_questions,
                "batch_rejected": total_rejected,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

            q_row = QuizQuestion(
                quiz_id=quiz.id,
                question_text=q_data["question_text"],
                options=json.dumps(q_data["options"]),
                correct_answer=q_data["correct_answer"],
                question_type=q_data["question_type"],
                question_order=idx,
                explanation=q_data["explanation"],
                points=q_data["points"],
                partial_credit_allowed=q_data["partial_credit_allowed"],
                difficulty=QuestionDifficulty(q_data["difficulty"]),
                status=ReviewStatus.pending_review,
                topic=t_name or (chunk.topic if chunk else None),
                topic_id=t_id,
                source_chunk_id=chunk.id if chunk else None,
                source_document_id=chunk.document_id if chunk else None,
                source_page_number=chunk.page_number if chunk else None,
                generation_meta=json.dumps(provenance_dict),
                version=1,
            )
            db.add(q_row)
            db.flush()

            if t_id:
                mapping = QuestionCurriculumMapping(
                    question_id=q_row.id,
                    topic_id=t_id,
                    subtopic_id=subtopic_id,
                    objective_id=objective_id,
                    bloom_level=effective_bloom,
                    weight=1.0,
                )
                db.add(mapping)

        db.commit()
        db.refresh(quiz)
    except Exception:
        db.rollback()
        raise

    setattr(quiz, "_requested_count", num_questions)
    setattr(quiz, "_rejected_count", total_rejected)
    logger.info("Quiz %s created with %d validated questions", quiz.id, len(accepted_pairs))
    return quiz


async def regenerate_question(
    db: Session,
    question: QuizQuestion,
    embedding_model: Any = None,
) -> QuizQuestion:
    """Regenerates a single pending or rejected question using its stored source chunk."""
    # Precondition 1: Status must be pending_review or rejected
    if question.status not in (ReviewStatus.pending_review, ReviewStatus.rejected):
        raise ValueError("Only pending or rejected questions can be regenerated")

    # Precondition 2: No student answers may reference this question
    existing_answers_count = (
        db.query(QuizAttemptAnswer)
        .filter(QuizAttemptAnswer.question_id == question.id)
        .count()
    )
    if existing_answers_count > 0:
        raise ValueError("This question already has student answers; edit it instead")

    # Precondition 3: Source chunk must be stored and exist
    if not question.source_chunk_id:
        raise ValueError("No source material stored for this question")

    chunk = db.get(Chunk, question.source_chunk_id)
    if not chunk:
        raise ValueError("No source material stored for this question")

    # Build single-chunk content
    sec = f" (Section: {chunk.section_title})" if chunk.section_title else ""
    pg = f" (Page {chunk.page_number})" if chunk.page_number is not None else ""
    chunk_text = (chunk.text or "")[:3000]
    content = f"[Source 1]{sec}{pg}\n{chunk_text}"

    # Build avoid block from class questions + current question text
    quiz = question.quiz
    class_id = str(quiz.class_id) if quiz and quiz.class_id else None
    existing_payloads = load_existing_question_payloads(db, class_id) if class_id else []
    avoid_texts = [p.get("question_text", "") for p in existing_payloads if p.get("question_text")]
    if question.question_text:
        avoid_texts.append(question.question_text)
    avoid_block = build_avoid_block(avoid_texts, max_items=15)

    prompt = QUIZ_GENERATION_PROMPT_V2.format(
        n=3,
        content=content,
        avoid_block=avoid_block,
    )

    provider, model_idx = rag_service.get_llm_provider()
    logger.info("Calling LLM to regenerate question %s (3 candidates requested)...", question.id)

    raw_output = None
    parsed: list[dict[str, Any]] | None = None
    for attempt in range(2):
        raw_output = await provider.generate(prompt, max_tokens=3000)
        try:
            parsed = _extract_json_array(raw_output)
            break
        except (ValueError, json.JSONDecodeError) as e:
            logger.warning("Regenerate attempt %d unparseable JSON: %s", attempt + 1, e)
            prompt = prompt + "\n\nIMPORTANT: respond with ONLY the JSON array, no preamble, no markdown."

    if parsed is None or not isinstance(parsed, list):
        raise ValueError(
            f"LLM failed to produce valid JSON after retries. Last output: {raw_output[:300] if raw_output else 'none'}"
        )

    from backend.llm.model_pool import model_pool

    tokens_used = rag_service.estimate_tokens(prompt) + rag_service.estimate_tokens(raw_output or "")
    model_pool.record_usage(model_idx, tokens_used)

    # Exclude the question being replaced from duplicate comparison
    existing_payloads_excl = [
        p for p in existing_payloads if str(p.get("id")) != str(question.id)
    ]

    class_subject = None
    if quiz and quiz.class_ and quiz.class_.subject:
        class_subject = quiz.class_.subject.name
    grounding_topic = question.topic or chunk.topic or class_subject or "Curriculum"

    chosen_candidate: dict[str, Any] | None = None
    rejection_reasons: list[str] = []

    for item in parsed:
        if not isinstance(item, dict):
            continue
        raw_q_text = str(item.get("question_text") or item.get("question") or "").strip()
        payload_dict = {
            "question_text": raw_q_text,
            "options": item.get("options"),
            "correct_answer": item.get("correct_answer"),
            "question_type": item.get("question_type") or "single_choice",
            "difficulty": item.get("difficulty") or "medium",
            "explanation": item.get("explanation"),
            "points": 1.0,
            "partial_credit_allowed": (item.get("question_type") == "multiple_choice"),
        }

        # 1. Schema
        try:
            validated = validate_and_normalize_question_payload(payload_dict)
        except ValueError as exc:
            rejection_reasons.append(f"Schema: {exc}")
            continue

        # 2. Duplicate
        is_dup, dup_reason = is_near_duplicate_question(validated, existing_payloads_excl)
        if is_dup:
            rejection_reasons.append(f"Duplicate: {dup_reason}")
            continue

        # 3. Grounding
        is_grounded, ground_reason = validate_chunk_grounding(validated, chunk, grounding_topic)
        if not is_grounded:
            rejection_reasons.append(f"Grounding: {ground_reason}")
            continue

        validated["bloom_level"] = item.get("bloom_level")
        validated["chunk_index"] = item.get("chunk_index")
        chosen_candidate = validated
        break

    if not chosen_candidate:
        top_reasons = "; ".join(rejection_reasons[:3]) if rejection_reasons else "Candidates failed validation"
        raise ValueError(f"Failed to generate a valid replacement question: {top_reasons}")

    try:
        norm = chosen_candidate
        bloom = calibrate_bloom_level(
            norm.get("bloom_level"), norm["question_text"], norm["difficulty"]
        )

        subtopic_id = None
        objective_id = None
        effective_bloom = bloom
        if question.topic_id:
            subtopic_id, objective_id, obj_bloom = match_objective_and_subtopic(
                db, question.topic_id, norm["question_text"], norm.get("explanation")
            )
            if not effective_bloom and obj_bloom:
                effective_bloom = obj_bloom

        provenance_dict = {
            "generator": "standard-regenerated",
            "prompt_version": "v2",
            "model_index": model_idx,
            "bloom_level": effective_bloom,
            "chunk_index": 1,
            "validation": {
                "schema": True,
                "duplicate_check": True,
                "grounding": True,
            },
            "batch_requested": 1,
            "batch_rejected": len(rejection_reasons),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        question.question_text = norm["question_text"]
        question.question_type = norm["question_type"]
        question.options = json.dumps(norm["options"])
        question.correct_answer = (
            json.dumps(norm["correct_answer"])
            if isinstance(norm["correct_answer"], list)
            else str(norm["correct_answer"])
        )
        question.points = float(norm["points"])
        question.partial_credit_allowed = bool(norm["partial_credit_allowed"])
        question.difficulty = QuestionDifficulty(norm["difficulty"])
        question.explanation = norm.get("explanation")
        question.version = (question.version or 1) + 1
        question.status = ReviewStatus.pending_review
        question.generation_meta = json.dumps(provenance_dict)
        question.updated_at = datetime.utcnow()

        # Update QuestionCurriculumMapping if exists
        mapping = (
            db.query(QuestionCurriculumMapping)
            .filter(QuestionCurriculumMapping.question_id == question.id)
            .first()
        )
        if mapping:
            mapping.bloom_level = effective_bloom
            if subtopic_id:
                mapping.subtopic_id = subtopic_id
            if objective_id:
                mapping.objective_id = objective_id

        db.commit()
        db.refresh(question)
        return question
    except Exception:
        db.rollback()
        raise


async def generate_topic_quiz(
    db: Session,
    class_id: str,
    topic: str,
    topic_id: str | None,
    student_user: User,
    embedding_model: Any,
    num_questions: int = 5,
) -> Quiz:
    """Generates a diagnostic practice quiz scoped strictly to a specific curriculum topic.
    Grounds questions in the class's approved/ready document chunks, enforces schema validation,
    preserves chunk provenance per question, and persists an approved topic-practice quiz.
    """
    print(f"[TOPIC QUIZ GEN] Starting: class={class_id} topic={topic!r} topic_id={topic_id} n={num_questions}")

    class_row = db.get(Class, uuid.UUID(str(class_id)))
    if class_row is None:
        raise ValueError(f"Class '{class_id}' not found.")

    subject = class_row.subject
    subject_id = str(class_row.subject_id) if class_row.subject_id else None
    if not subject and not subject_id:
        raise ValueError(f"Class '{class_id}' does not have a curriculum subject configured.")

    # Validate and resolve canonical topic
    topic_row: PrerequisiteMap | None = None
    if topic_id:
        topic_row = db.get(PrerequisiteMap, uuid.UUID(str(topic_id)))
        if not topic_row:
            raise ValueError(f"Topic ID '{topic_id}' not found.")
        if class_row.subject_id and topic_row.subject_id and topic_row.subject_id != class_row.subject_id:
            raise ValueError(f"Topic '{topic_row.topic}' does not belong to this class's subject curriculum.")
    elif topic and topic.strip() and class_row.subject_id:
        topic_row = (
            db.query(PrerequisiteMap)
            .filter(
                PrerequisiteMap.subject_id == class_row.subject_id,
                PrerequisiteMap.topic.ilike(topic.strip()),
            )
            .first()
        )

    canonical_topic = topic_row.topic if topic_row else topic.strip()
    canonical_topic_id = topic_row.id if topic_row else None
    unit = topic_row.unit if topic_row else None
    source_doc_id = topic_row.source_document_id if topic_row else None
    subtopics = [s.name for s in topic_row.subtopics] if topic_row and topic_row.subtopics else []
    objectives = [obj.statement for obj in topic_row.learning_objectives] if topic_row and topic_row.learning_objectives else []

    # Grounded multi-tier retrieval scoped to class curriculum
    chunks_with_sim = retrieve_topic_grounded_chunks(
        db=db,
        class_id=class_row.id,
        subject=subject,
        subject_id=subject_id,
        canonical_topic=canonical_topic,
        topic_row=topic_row,
        embedding_model=embedding_model,
        top_k=6,
    )

    if not chunks_with_sim:
        raise ValueError(
            f"No curriculum materials found for topic '{canonical_topic}'. "
            "Please ask your educator to upload syllabus or study materials for this topic."
        )
    total_chars = sum(len(c.text or "") for c, _ in chunks_with_sim)
    if total_chars < 50:
        raise ValueError(
            f"No curriculum materials found for topic '{canonical_topic}' with sufficient content. "
            "Please ask your educator to upload complete study materials for this topic."
        )

    # Format chunks with numbered sources for prompt
    source_blocks = []
    for idx, (chunk, _sim) in enumerate(chunks_with_sim, start=1):
        heading = f" (Section: {chunk.section_heading})" if chunk.section_heading else ""
        page = f" (Page {chunk.page_number})" if chunk.page_number else ""
        source_blocks.append(f"[Source {idx}]{heading}{page}\n{chunk.text}")
    content = "\n\n".join(source_blocks)

    # Request surplus candidates to allow filtering near-duplicates or ungrounded questions
    request_candidates_count = max(num_questions + 3, int(num_questions * 1.5))
    prompt = TOPIC_QUIZ_PROMPT_TEMPLATE.format(
        topic=canonical_topic,
        n=request_candidates_count,
        content=content[:5000],
    )

    provider, model_idx = rag_service.get_llm_provider()
    print(f"[TOPIC QUIZ GEN] Requesting LLM generation for topic={canonical_topic!r} (requesting {request_candidates_count} items)...")

    raw_output = None
    parsed: list[dict[str, Any]] | None = None
    for attempt in range(2):
        raw_output = await provider.generate(prompt, max_tokens=2500)
        try:
            parsed = _extract_json_array(raw_output)
            break
        except (ValueError, json.JSONDecodeError) as e:
            print(f"[TOPIC QUIZ GEN WARNING] Attempt {attempt + 1} produced unparseable JSON: {e}")
            prompt = prompt + "\n\nIMPORTANT: respond with ONLY the JSON array, no preamble, no markdown formatting."

    if parsed is None or not isinstance(parsed, list):
        raise ValueError(
            f"LLM failed to produce valid question JSON. Output: {raw_output[:300] if raw_output else 'none'}"
        )

    from backend.llm.model_pool import model_pool

    tokens_used = rag_service.estimate_tokens(prompt) + rag_service.estimate_tokens(raw_output or "")
    model_pool.record_usage(model_idx, tokens_used)
    print(f"[TOPIC QUIZ GEN] LLM returned {len(parsed)} candidate items (~{tokens_used} tokens)")

    # Validate each candidate item through the validation and grounding pipeline
    accepted_pairs: list[tuple[dict[str, Any], Chunk, str]] = []
    rejection_log: list[dict[str, str]] = []
    accepted_payloads: list[dict[str, Any]] = []

    for item in parsed:
        if not isinstance(item, dict):
            continue
        raw_q_text = str(item.get("question") or item.get("question_text") or "").strip()
        payload_dict = {
            "question_text": raw_q_text,
            "options": item.get("options"),
            "correct_answer": item.get("correct_answer"),
            "question_type": item.get("question_type") or "single_choice",
            "difficulty": item.get("difficulty") or "medium",
            "explanation": item.get("explanation"),
            "points": 1.0,
            "partial_credit_allowed": (item.get("question_type") == "multiple_choice"),
        }
        try:
            validated = validate_and_normalize_question_payload(payload_dict)
        except ValueError as exc:
            rejection_log.append({"question": raw_q_text[:60], "reason": f"Schema: {exc}"})
            continue

        # Near-duplicate check against already accepted questions
        is_dup, dup_reason = is_near_duplicate_question(validated, accepted_payloads)
        if is_dup:
            rejection_log.append({"question": validated["question_text"][:60], "reason": f"Duplicate: {dup_reason}"})
            continue

        # Attribute supporting chunk with grounding fallback
        assigned_chunk: Chunk | None = None
        c_idx = item.get("chunk_index")
        if isinstance(c_idx, int) and 1 <= c_idx <= len(chunks_with_sim):
            candidate_chunk = chunks_with_sim[c_idx - 1][0]
            is_ok, _ = validate_chunk_grounding(validated, candidate_chunk, canonical_topic)
            if is_ok:
                assigned_chunk = candidate_chunk

        if not assigned_chunk:
            assigned_chunk = _find_best_supporting_chunk(
                validated["question_text"], validated.get("explanation") or "", chunks_with_sim
            )

        # Validate chunk grounding (hallucination guard)
        is_grounded, ground_reason = validate_chunk_grounding(validated, assigned_chunk, canonical_topic)
        if not is_grounded:
            rejection_log.append({"question": validated["question_text"][:60], "reason": f"Grounding: {ground_reason}"})
            continue

        # Extract or calibrate Bloom's taxonomy level
        raw_bloom = str(item.get("bloom_level") or "").strip().lower()
        if raw_bloom in {"remember", "understand", "apply", "analyze"}:
            bloom_level = raw_bloom
        else:
            q_lower = validated["question_text"].lower()
            if any(kw in q_lower for kw in ["compare", "differentiate", "analyze", "why does", "break down"]):
                bloom_level = "analyze"
            elif any(kw in q_lower for kw in ["apply", "scenario", "calculate", "if a student", "given that"]):
                bloom_level = "apply"
            elif any(kw in q_lower for kw in ["explain", "describe", "interpret", "meaning"]):
                bloom_level = "understand"
            elif validated["difficulty"] == "hard":
                bloom_level = "analyze"
            elif validated["difficulty"] == "medium":
                bloom_level = "apply"
            else:
                bloom_level = "remember"

        accepted_pairs.append((validated, assigned_chunk, bloom_level))
        accepted_payloads.append(validated)
        if len(accepted_pairs) >= num_questions:
            break

    if not accepted_pairs:
        failure_summary = "; ".join(r["reason"] for r in rejection_log[:3])
        raise ValueError(
            f"No valid diagnostic questions could be generated from curriculum materials for '{canonical_topic}'. "
            f"Candidates evaluated: {len(parsed)}. Failure details: {failure_summary}"
        )

    # Persist Practice Quiz
    primary_doc_id = source_doc_id or (accepted_pairs[0][1].document_id if accepted_pairs[0][1] else None)

    generation_metadata = {
        "type": "topic_practice",
        "canonical_topic": canonical_topic,
        "topic_id": str(canonical_topic_id) if canonical_topic_id else None,
        "model_idx": model_idx,
        "prompt_version": "v3.0-grounded-diversity",
        "retrieved_chunks_count": len(chunks_with_sim),
        "candidates_evaluated": len(parsed),
        "accepted_count": len(accepted_pairs),
        "rejected_count": len(rejection_log),
        "rejection_sample": rejection_log[:5],
    }

    quiz = Quiz(
        title=f"Practice: {canonical_topic}",
        description=json.dumps(generation_metadata),
        unit=unit,
        chapter=None,
        generation_type="topic_practice",
        status=ReviewStatus.approved,
        version=1,
        time_limit_minutes=None,
        passing_percentage=60.0,
        class_id=class_row.id,
        document_id=primary_doc_id,
        created_by_id=student_user.id,
    )
    db.add(quiz)
    db.flush()

    for idx, (q_data, chunk, bloom) in enumerate(accepted_pairs, start=1):
        q_row = QuizQuestion(
            quiz_id=quiz.id,
            question_text=q_data["question_text"],
            options=json.dumps(q_data["options"]),
            correct_answer=q_data["correct_answer"],
            question_type=q_data["question_type"],
            question_order=idx,
            explanation=q_data["explanation"],
            points=q_data["points"],
            partial_credit_allowed=q_data["partial_credit_allowed"],
            difficulty=QuestionDifficulty(q_data["difficulty"]),
            status=ReviewStatus.approved,
            topic=canonical_topic,
            topic_id=canonical_topic_id,
            source_chunk_id=chunk.id if chunk else None,
            source_document_id=chunk.document_id if chunk else None,
            source_page_number=chunk.page_number if chunk else None,
            version=1,
        )
        db.add(q_row)
        db.flush()

        if canonical_topic_id:
            mapping = QuestionCurriculumMapping(
                question_id=q_row.id,
                topic_id=canonical_topic_id,
                bloom_level=bloom,
                weight=1.0,
            )
            db.add(mapping)

    db.commit()
    db.refresh(quiz)
    print(f"[TOPIC QUIZ GEN SUCCESS] Created practice quiz {quiz.id} with {len(quiz.questions)} questions")
    return quiz


TOPIC_PASS_THRESHOLD = 0.5


def available_questions_for_student(
    db: Session, quiz: Quiz, student_id: str, class_id: str
) -> list[QuizQuestion]:
    if getattr(quiz, "generation_type", None) == "topic_practice":
        return [q for q in quiz.questions if q.status == ReviewStatus.approved]
    locked = routing_service.intervene_topics(db, student_id, class_id)
    return [
        q
        for q in quiz.questions
        if q.status == ReviewStatus.approved and (q.topic not in locked if (q.topic and q.topic.strip()) else True)
    ]


async def run_background_misconception_detection(
    student_id: str,
    class_id: str,
    source_attempt_id: str | None,
    candidates: list[dict[str, Any]],
) -> None:
    """
    Background worker to evaluate wrong answers using LLM fallback
    without blocking the synchronous quiz submission HTTP response.
    """
    to_evaluate = candidates[:3]
    if not to_evaluate:
        return

    from backend.core.database import SessionLocal

    print(f"[QUIZ MISCONCEPTION BG] Running AI detection for {len(to_evaluate)} candidate(s)...")
    db = SessionLocal()
    try:
        for item in to_evaluate:
            topic = item.get("topic")
            if not topic or topic.strip().lower() == "general":
                continue
            try:
                ai_result = await misconception_service.detect_misconception_ai(
                    item["question_text"],
                    item["chosen"],
                    item["correct_answer"],
                    item["question_text"],
                )
                if ai_result and ai_result.get("description"):
                    misconception_service.record_misconception(
                        db, student_id, class_id, topic, ai_result["description"], source_attempt_id
                    )
            except Exception as e:
                print(f"[QUIZ MISCONCEPTION BG WARNING] AI detection failed for item: {e}")
    finally:
        db.close()


def evaluate_question_answer(question: QuizQuestion, chosen: Any) -> tuple[bool, float]:
    """Evaluates a student's answer against a QuizQuestion.
    Returns: (is_correct: bool, credit_fraction: float)
    - Single choice / True-False: exact match yields (True, 1.0), else (False, 0.0)
    - Multiple choice:
        If partial_credit_allowed:
            (matched - wrong) / total_correct clamped to [0.0, 1.0]
            is_correct is True if credit_fraction >= 1.0
        Else:
            chosen_norm == corr_norm yields (True, 1.0), else (False, 0.0)
    """
    raw_type = getattr(question, "question_type", "single_choice")
    q_type = (raw_type.value if hasattr(raw_type, "value") else str(raw_type)).lower()

    if "multiple_choice" in q_type:
        try:
            corr_list = json.loads(question.correct_answer) if str(question.correct_answer).startswith("[") else [s.strip() for s in question.correct_answer.split(",")]
        except Exception:
            corr_list = [question.correct_answer]
        corr_norm = {_normalize_answer(s) for s in corr_list if s}

        if isinstance(chosen, (list, tuple)):
            chosen_set = {str(c) for c in chosen}
        elif isinstance(chosen, str) and chosen.strip().startswith("["):
            try:
                chosen_set = set(json.loads(chosen))
            except Exception:
                chosen_set = {chosen}
        elif isinstance(chosen, str) and "," in chosen:
            chosen_set = {s.strip() for s in chosen.split(",")}
        elif chosen is not None:
            chosen_set = {str(chosen)}
        else:
            chosen_set = set()
        chosen_norm = {_normalize_answer(s) for s in chosen_set if s}

        if not corr_norm:
            return False, 0.0

        if getattr(question, "partial_credit_allowed", False):
            matched = len(chosen_norm & corr_norm)
            wrong = len(chosen_norm - corr_norm)
            credit = max(0.0, (matched - wrong) / len(corr_norm))
            return credit >= 1.0, credit
        else:
            correct = chosen_norm == corr_norm and len(corr_norm) > 0
            return correct, 1.0 if correct else 0.0
    else:
        correct = chosen is not None and _normalize_answer(str(chosen)) == _normalize_answer(str(question.correct_answer))
        return correct, 1.0 if correct else 0.0


async def score_attempt(
    db: Session,
    quiz: Quiz,
    student_id: str,
    class_id: str,
    answers: dict[str, str],
    source_attempt_id: str | None = None,
) -> dict[str, Any]:
    print(f"[QUIZ SCORE] Scoring attempt for quiz={quiz.id} student={student_id}")

    approved_questions = available_questions_for_student(db, quiz, student_id, class_id)
    if not approved_questions:
        raise ValueError(
            "No questions are available on this quiz right now. Topics with an unresolved "
            "misconception are unlocked by working through them in a guided (Socratic) chat session."
        )

    class_row = db.get(Class, class_id)
    subject_id = str(class_row.subject_id) if class_row and class_row.subject_id else None

    topic_earned: dict[str, float] = {}
    topic_total: dict[str, float] = {}
    total_earned_points = 0.0
    total_max_points = 0.0
    total_correct = 0
    per_question_results = []
    ai_candidates = []

    for question in approved_questions:
        chosen = answers.get(str(question.id))
        is_correct, credit_fraction = evaluate_question_answer(question, chosen)
        points_possible = float(getattr(question, "points", 1.0) or 1.0)
        earned_points = credit_fraction * points_possible

        total_earned_points += earned_points
        total_max_points += points_possible

        # Resolve topic name: question.topic or curriculum mapping
        raw_topic = question.topic.strip() if question.topic and question.topic.strip() else None
        if not raw_topic and getattr(question, "curriculum_mappings", None):
            for m in question.curriculum_mappings:
                if getattr(m, "topic", None):
                    raw_topic = m.topic.topic
                    break
                elif getattr(m, "topic_id", None):
                    top_row = db.get(PrerequisiteMap, m.topic_id)
                    if top_row:
                        raw_topic = top_row.topic
                        break

        if raw_topic and raw_topic.lower() != "general":
            topic_total[raw_topic] = topic_total.get(raw_topic, 0.0) + points_possible
            topic_earned[raw_topic] = topic_earned.get(raw_topic, 0.0) + earned_points

        if is_correct:
            total_correct += 1
            if raw_topic and raw_topic.lower() != "general":
                misconception_service.resolve_misconceptions_for_correct_answer(db, student_id, class_id, raw_topic)
        elif chosen is not None and raw_topic:
            if subject_id:
                description = misconception_service.check_rules_db(
                    db, subject_id, raw_topic, question.question_text, chosen
                )
            else:
                description = misconception_service.check_rule_map(
                    raw_topic, question.question_text, chosen, question.correct_answer
                )
            if description:
                misconception_service.record_misconception(
                    db, student_id, class_id, raw_topic, description, source_attempt_id
                )
            else:
                ai_candidates.append({
                    "question_text": question.question_text,
                    "chosen": chosen,
                    "correct_answer": question.correct_answer,
                    "topic": raw_topic,
                })

        try:
            options_list = json.loads(question.options) if question.options else []
        except Exception:
            options_list = []
        diff_val = question.difficulty.value if hasattr(question.difficulty, "value") else str(question.difficulty)

        q_type = getattr(question, "question_type", "single_choice") or "single_choice"
        if hasattr(q_type, "value"):
            q_type = q_type.value

        formatted_correct_answer = question.correct_answer
        if q_type == "multiple_choice" and question.correct_answer and str(question.correct_answer).startswith("["):
            try:
                parsed_corr = json.loads(question.correct_answer)
                if isinstance(parsed_corr, list):
                    formatted_correct_answer = parsed_corr
            except Exception:
                formatted_correct_answer = question.correct_answer

        formatted_chosen = chosen
        if isinstance(chosen, str) and chosen.startswith("["):
            try:
                parsed_ch = json.loads(chosen)
                if isinstance(parsed_ch, list):
                    formatted_chosen = parsed_ch
            except Exception:
                formatted_chosen = chosen

        per_question_results.append({
            "question_id": str(question.id),
            "correct": is_correct,
            "correct_answer": formatted_correct_answer,
            "chosen": formatted_chosen,
            "topic": raw_topic or question.topic or "Unmapped",
            "difficulty": diff_val,
            "option_count": len(options_list) if options_list else None,
            "credit_fraction": credit_fraction,
            "earned_points": earned_points,
            "points_possible": points_possible,
            "question_type": q_type,
            "explanation": getattr(question, "explanation", None),
        })

    if not topic_total:
        overall_frac = (total_earned_points / total_max_points) if total_max_points > 0 else 0.0
        topic_scores = {"General": round(overall_frac, 3)}
        topic_passed = {"General": overall_frac >= TOPIC_PASS_THRESHOLD}
    else:
        topic_scores = {t: round(topic_earned.get(t, 0.0) / topic_total[t], 3) for t in topic_total}
        topic_passed = {t: score >= TOPIC_PASS_THRESHOLD for t, score in topic_scores.items()}

    overall_score = round((total_earned_points / total_max_points) * 100, 1) if total_max_points > 0 else 0.0

    print(f"[QUIZ SCORE] Overall={overall_score:.1f}% topic_scores={topic_scores} passed={topic_passed}")

    return {
        "score": overall_score,
        "total_earned_points": total_earned_points,
        "total_max_points": total_max_points,
        "topic_scores": topic_scores,
        "topic_passed": topic_passed,
        "results": per_question_results,
        "ai_candidates": ai_candidates,
    }


def build_answer_rows(
    attempt_id: str,
    student_id: str,
    results: list[dict[str, Any]],
    answered_at: datetime | None = None,
    class_id: str | None = None,
) -> list[dict[str, Any]]:
    from backend.services.mastery_v2 import normalize_topic_key

    timestamp = answered_at or datetime.now(timezone.utc)
    class_uuid = uuid.UUID(class_id) if isinstance(class_id, str) else class_id
    rows = []
    for item in results:
        topic = item.get("topic")
        chosen = item.get("chosen")
        if chosen is None:
            selected_options = None
        elif isinstance(chosen, (list, tuple)):
            selected_options = json.dumps(chosen) if len(chosen) > 0 else None
        else:
            s = str(chosen)
            selected_options = s if s != "" else None

        points_awarded = item.get("earned_points")
        max_points = item.get("points_possible")

        rows.append({
            "id": uuid.uuid4(),
            "attempt_id": uuid.UUID(attempt_id) if isinstance(attempt_id, str) else attempt_id,
            "student_id": uuid.UUID(student_id) if isinstance(student_id, str) else student_id,
            "class_id": class_uuid,
            "question_id": uuid.UUID(item["question_id"]) if isinstance(item["question_id"], str) else item["question_id"],
            "topic": topic,
            "topic_key": normalize_topic_key(topic),
            "is_correct": bool(item.get("correct", False)),
            "points_awarded": float(points_awarded) if points_awarded is not None else None,
            "max_points": float(max_points) if max_points is not None else None,
            "difficulty": item.get("difficulty"),
            "option_count": item.get("option_count"),
            "selected_options": selected_options,
            "answered_at": timestamp,
        })
    return rows
