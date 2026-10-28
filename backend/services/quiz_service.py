import json
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.models.db import Class, Quiz, QuizQuestion, ReviewStatus
from backend.services import context_service, misconception_service, rag_service, routing_service

QUIZ_GENERATION_PROMPT_TEMPLATE = (
    "Generate {n} multiple-choice questions testing understanding of the curriculum content below. "
    "Return ONLY a JSON array, no other text, no markdown formatting. "
    "Each item: {{\"question\": str, \"options\": [4 strings], \"correct_answer\": str (must exactly match one option), "
    "\"difficulty\": \"easy\"|\"medium\"|\"hard\"}}.\n\n"
    "Curriculum content:\n{content}"
)


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
    print(f"[QUIZ GEN] Starting generation: class={class_id} unit={unit} chapter={chapter} n={num_questions}")

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
        db, subject, seed_vector, top_k=6, chapter_scope=[chapter], subject_id=subject_id, class_id=class_id
    )

    content = "\n\n".join(chunk.text for chunk, _sim in chunks_with_sim)
    if not content.strip():
        raise ValueError(f"No curriculum content found for subject={subject} chapter={chapter} — upload a document first.")

    prompt = QUIZ_GENERATION_PROMPT_TEMPLATE.format(n=num_questions, content=content[:4000])

    provider, model_idx = rag_service.get_llm_provider()
    print(f"[QUIZ GEN] Calling LLM for {num_questions} questions...")

    raw_output = None
    parsed: list[dict[str, Any]] | None = None
    for attempt in range(2):
        raw_output = await provider.generate(prompt, max_tokens=2000)
        try:
            parsed = _extract_json_array(raw_output)
            break
        except (ValueError, json.JSONDecodeError) as e:
            print(f"[QUIZ GEN WARNING] Attempt {attempt + 1} produced unparseable JSON: {e}")
            prompt = prompt + "\n\nIMPORTANT: respond with ONLY the JSON array, no preamble, no markdown."

    if parsed is None:
        raise ValueError(f"LLM failed to produce valid JSON after retries. Last output: {raw_output[:300] if raw_output else 'none'}")

    from backend.llm.model_pool import model_pool

    tokens_used = rag_service.estimate_tokens(prompt) + rag_service.estimate_tokens(raw_output)
    model_pool.record_usage(model_idx, tokens_used)
    print(f"[QUIZ GEN] Parsed {len(parsed)} questions, ~{tokens_used} tokens used")

    validated_questions: list[dict[str, Any]] = []
    for item in parsed:
        cleaned = _validate_generated_question(item)
        if cleaned is None:
            print(f"[QUIZ GEN WARNING] Skipping malformed question: {item}")
            continue
        validated_questions.append(cleaned)

    if not validated_questions:
        raise ValueError("No valid questions could be generated from the curriculum content.")

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

    source_chunk = chunks_with_sim[0][0] if chunks_with_sim else None
    source_chunk_id = source_chunk.id if source_chunk else None
    source_chunk_topic = source_chunk.topic if source_chunk else None

    created_count = 0
    for q_data in validated_questions:
        question_text = q_data["question"]
        options = q_data["options"]
        correct_answer = q_data["correct_answer"]
        difficulty = q_data["difficulty"]

        if subject_id:
            topic = (
                context_service.detect_topic_for_subject(db, question_text, subject_id, embedding_model)
                or source_chunk_topic
            )
        else:
            topic = context_service.detect_topic(question_text, subject or "") or source_chunk_topic

        db.add(
            QuizQuestion(
                quiz_id=quiz.id,
                question_text=question_text,
                options=json.dumps(options),
                correct_answer=correct_answer,
                topic=topic,
                difficulty=difficulty,
                status=ReviewStatus.pending_review,
                source_chunk_id=source_chunk_id,
            )
        )
        created_count += 1

    db.commit()
    db.refresh(quiz)
    print(f"[QUIZ GEN SUCCESS] Quiz {quiz.id} created with {created_count} questions")
    return quiz


TOPIC_PASS_THRESHOLD = 0.5


def available_questions_for_student(
    db: Session, quiz: Quiz, student_id: str, class_id: str
) -> list[QuizQuestion]:
    locked = routing_service.intervene_topics(db, student_id, class_id)
    return [
        q
        for q in quiz.questions
        if q.status == ReviewStatus.approved and (q.topic or "General") not in locked
    ]


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

    topic_correct: dict[str, int] = {}
    topic_total: dict[str, int] = {}
    total_correct = 0
    per_question_results = []

    for question in approved_questions:
        chosen = answers.get(str(question.id))
        is_correct = chosen is not None and _normalize_answer(chosen) == _normalize_answer(question.correct_answer)
        topic = question.topic or "General"

        topic_total[topic] = topic_total.get(topic, 0) + 1
        if is_correct:
            total_correct += 1
            topic_correct[topic] = topic_correct.get(topic, 0) + 1
            misconception_service.resolve_misconceptions_for_correct_answer(db, student_id, class_id, topic)
        elif chosen is not None:
            if subject_id:
                description = misconception_service.check_rules_db(
                    db, subject_id, topic, question.question_text, chosen
                )
            else:
                description = misconception_service.check_rule_map(
                    topic, question.question_text, chosen, question.correct_answer
                )
            if description is None:
                ai_result = await misconception_service.detect_misconception_ai(
                    question.question_text, chosen, question.correct_answer, question.question_text
                )
                if ai_result:
                    description = ai_result["description"]
            if description:
                misconception_service.record_misconception(
                    db, student_id, class_id, topic, description, source_attempt_id
                )

        try:
            options_list = json.loads(question.options) if question.options else []
        except Exception:
            options_list = []
        diff_val = question.difficulty.value if hasattr(question.difficulty, "value") else str(question.difficulty)
        per_question_results.append({
            "question_id": str(question.id),
            "correct": is_correct,
            "correct_answer": question.correct_answer,
            "chosen": chosen,
            "topic": question.topic,
            "difficulty": diff_val,
            "option_count": len(options_list) if options_list else None,
        })

    topic_scores = {t: topic_correct.get(t, 0) / topic_total[t] for t in topic_total}
    topic_passed = {t: score >= TOPIC_PASS_THRESHOLD for t, score in topic_scores.items()}
    overall_score = (total_correct / len(approved_questions)) * 100

    print(f"[QUIZ SCORE] Overall={overall_score:.1f}% topic_scores={topic_scores} passed={topic_passed}")

    return {
        "score": overall_score,
        "topic_scores": topic_scores,
        "topic_passed": topic_passed,
        "results": per_question_results,
    }


def build_answer_rows(
    attempt_id: str,
    student_id: str,
    results: list[dict[str, Any]],
    answered_at: datetime | None = None,
) -> list[dict[str, Any]]:
    from backend.services.mastery_v2 import normalize_topic_key

    timestamp = answered_at or datetime.utcnow()
    rows = []
    for item in results:
        topic = item.get("topic")
        rows.append({
            "id": uuid.uuid4(),
            "attempt_id": uuid.UUID(attempt_id) if isinstance(attempt_id, str) else attempt_id,
            "student_id": uuid.UUID(student_id) if isinstance(student_id, str) else student_id,
            "question_id": uuid.UUID(item["question_id"]) if isinstance(item["question_id"], str) else item["question_id"],
            "topic": topic,
            "topic_key": normalize_topic_key(topic),
            "is_correct": bool(item.get("correct", False)),
            "difficulty": item.get("difficulty"),
            "option_count": item.get("option_count"),
            "answered_at": timestamp,
        })
    return rows
