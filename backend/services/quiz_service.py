import json
import re
from typing import Any

from sqlalchemy.orm import Session

from backend.models.db import Class, Document, Quiz, QuizAttempt, QuizQuestion, ReviewStatus
from backend.services import context_service, misconception_service, rag_service

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
    subject = class_row.subject or "Operating Systems"

    from backend.pipeline.embedder import embed_single

    seed_vector = embed_single(f"{subject} chapter {chapter}", model=embedding_model)
    chunks_with_sim = rag_service.retrieve_chunks(db, subject, seed_vector, top_k=6, chapter_scope=[chapter])
    if not chunks_with_sim:
        chunks_with_sim = rag_service.retrieve_chunks(db, subject, seed_vector, top_k=6)

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

    source_chunk_id = chunks_with_sim[0][0].id if chunks_with_sim else None

    created_count = 0
    for item in parsed:
        try:
            question_text = item["question"]
            options = item["options"]
            correct_answer = item["correct_answer"]
            difficulty = item.get("difficulty", "medium")
            if correct_answer not in options or len(options) != 4:
                print(f"[QUIZ GEN WARNING] Skipping malformed question: {item}")
                continue
        except (KeyError, TypeError):
            print(f"[QUIZ GEN WARNING] Skipping malformed question: {item}")
            continue

        topic = context_service.detect_topic(question_text, subject) or class_row.subject

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


async def score_attempt(
    db: Session, quiz: Quiz, student_id: str, class_id: str, answers: dict[str, str]
) -> dict[str, Any]:
    print(f"[QUIZ SCORE] Scoring attempt for quiz={quiz.id} student={student_id}")

    approved_questions = [q for q in quiz.questions if q.status == ReviewStatus.approved]
    if not approved_questions:
        raise ValueError("This quiz has no approved questions yet.")

    topic_correct: dict[str, int] = {}
    topic_total: dict[str, int] = {}
    total_correct = 0
    per_question_results = []

    for question in approved_questions:
        chosen = answers.get(str(question.id))
        is_correct = chosen == question.correct_answer
        topic = question.topic or "General"

        topic_total[topic] = topic_total.get(topic, 0) + 1
        if is_correct:
            total_correct += 1
            topic_correct[topic] = topic_correct.get(topic, 0) + 1
            misconception_service.resolve_misconceptions_for_correct_answer(db, student_id, class_id, topic)
        elif chosen is not None:
            description = misconception_service.check_rule_map(topic, question.question_text, chosen, question.correct_answer)
            if description is None:
                curriculum_context = question.question_text
                ai_result = await misconception_service.detect_misconception_ai(
                    question.question_text, chosen, question.correct_answer, curriculum_context
                )
                if ai_result:
                    description = ai_result["description"]
            if description:
                misconception_service.record_misconception(db, student_id, class_id, topic, description, None)

        per_question_results.append({
            "question_id": str(question.id),
            "correct": is_correct,
            "correct_answer": question.correct_answer,
            "chosen": chosen,
        })

    topic_scores = {t: topic_correct.get(t, 0) / topic_total[t] for t in topic_total}
    overall_score = (total_correct / len(approved_questions)) * 100

    print(f"[QUIZ SCORE] Overall={overall_score:.1f}% topic_scores={topic_scores}")

    return {
        "score": overall_score,
        "topic_scores": topic_scores,
        "results": per_question_results,
    }
