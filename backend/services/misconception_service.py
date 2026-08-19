from typing import Any

from sqlalchemy.orm import Session

from backend.llm.prompts import MISCONCEPTION_PROMPT
from backend.models.db import Misconception

MISCONCEPTION_MAP: dict[str, list[dict[str, Any]]] = {
    "SJF": [
        {
            "trigger": lambda q, wrong, correct: "arrival" in wrong.lower() and "burst" in correct.lower(),
            "description": "Conflates burst time with arrival time in SJF",
        },
        {
            "trigger": lambda q, wrong, correct: "preemptive" in q.lower() and wrong != correct,
            "description": "Does not distinguish preemptive vs non-preemptive SJF",
        },
    ],
    "Round Robin": [
        {
            "trigger": lambda q, wrong, correct: "quantum" in q.lower() and wrong != correct,
            "description": "Misunderstands time quantum selection effect",
        },
    ],
    "Deadlock Detection": [
        {
            "trigger": lambda q, wrong, correct: any(
                c in wrong.lower()
                for c in ["mutual exclusion", "hold and wait", "circular wait", "no preemption"]
            ),
            "description": "Confuses the four necessary conditions for deadlock",
        },
    ],
    "Paging": [
        {
            "trigger": lambda q, wrong, correct: "segmentation" in wrong.lower() and "paging" in q.lower(),
            "description": "Confuses paging with segmentation",
        },
    ],
}


def check_rule_map(topic: str | None, question_text: str, wrong_answer: str, correct_answer: str) -> str | None:
    if not topic or topic not in MISCONCEPTION_MAP:
        return None
    for rule in MISCONCEPTION_MAP[topic]:
        try:
            if rule["trigger"](question_text, wrong_answer, correct_answer):
                print(f"[MISCONCEPTION] Rule map matched for topic={topic!r}: {rule['description']}")
                return rule["description"]
        except Exception as e:
            print(f"[MISCONCEPTION WARNING] Rule evaluation failed for topic={topic!r}: {e}")
            continue
    return None


async def detect_misconception_ai(
    question_text: str,
    wrong_answer: str,
    correct_answer: str,
    curriculum_context: str,
) -> dict[str, Any] | None:
    from backend.services.rag_service import get_llm_provider

    prompt = (
        f"{MISCONCEPTION_PROMPT}\n\n"
        f"Curriculum context: {curriculum_context}\n"
        f"Question: {question_text}\n"
        f"Student's answer: {wrong_answer}\n"
        f"Correct answer: {correct_answer}"
    )

    provider, model_idx = get_llm_provider()
    print(f"[MISCONCEPTION] No rule-map match — falling back to AI evaluation (~175 tokens)")
    try:
        response_text = await provider.generate(prompt, max_tokens=100)
    except Exception as e:
        print(f"[MISCONCEPTION ERROR] AI fallback call failed: {e}")
        return None

    from backend.llm.model_pool import model_pool

    tokens_used = len(prompt.split()) + len(response_text.split())
    model_pool.record_usage(model_idx, tokens_used)

    result = _parse_misconception_response(response_text)
    print(f"[MISCONCEPTION] AI fallback result: {result}")
    return result


def _parse_misconception_response(text: str) -> dict[str, Any] | None:
    lines = text.strip().splitlines()
    parsed: dict[str, str] = {}
    for line in lines:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        parsed[key.strip().upper()] = value.strip()

    misconception = parsed.get("MISCONCEPTION", "none")
    if not misconception or misconception.lower() == "none":
        return None

    return {
        "description": parsed.get("EXPLANATION", misconception),
        "resolved": parsed.get("RESOLVED", "false").lower() == "true",
    }


def record_misconception(
    db: Session, student_id: str, class_id: str, topic: str, description: str, source_quiz_attempt_id: str | None
) -> None:
    existing = (
        db.query(Misconception)
        .filter(
            Misconception.student_id == student_id,
            Misconception.class_id == class_id,
            Misconception.topic == topic,
            Misconception.description == description,
            Misconception.resolved == False,  # noqa: E712
        )
        .first()
    )
    if existing:
        print(f"[MISCONCEPTION] Already logged and unresolved for student={student_id} topic={topic} — skipping duplicate")
        return

    db.add(
        Misconception(
            student_id=student_id,
            class_id=class_id,
            topic=topic,
            description=description,
            source_quiz_attempt_id=source_quiz_attempt_id,
            resolved=False,
        )
    )
    db.commit()
    print(f"[MISCONCEPTION SUCCESS] Logged for student={student_id} topic={topic}: {description}")


def resolve_misconceptions_for_correct_answer(db: Session, student_id: str, class_id: str, topic: str) -> None:
    updated = (
        db.query(Misconception)
        .filter(
            Misconception.student_id == student_id,
            Misconception.class_id == class_id,
            Misconception.topic == topic,
            Misconception.resolved == False,  # noqa: E712
        )
        .update({"resolved": True})
    )
    if updated:
        db.commit()
        print(f"[MISCONCEPTION] Resolved {updated} misconception(s) for student={student_id} topic={topic} (correct answer given)")
