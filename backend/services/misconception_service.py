import json
import re
from typing import Any

from sqlalchemy.orm import Session

from backend.llm.prompts import MISCONCEPTION_PROMPT
from backend.models.db import Misconception, MisconceptionRule

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
                print(f"[MISCONCEPTION] Legacy rule map matched for topic={topic!r}: {rule['description']}")
                return rule["description"]
        except Exception as e:
            print(f"[MISCONCEPTION WARNING] Rule evaluation failed for topic={topic!r}: {e}")
            continue
    return None


def _kw_hit(text: str, keywords: list[str] | None) -> bool:
    if not keywords:
        return False
    lowered = text.lower()
    return any(k.lower() in lowered for k in keywords if k)


def check_rules_db(
    db: Session, subject_id: str, topic: str | None, question_text: str, wrong_answer: str
) -> str | None:
    if not topic:
        return None
    rows = (
        db.query(MisconceptionRule)
        .filter(MisconceptionRule.subject_id == subject_id, MisconceptionRule.topic == topic)
        .all()
    )
    for rule in rows:
        if not _kw_hit(wrong_answer, rule.wrong_answer_keywords):
            continue
        if rule.question_keywords and not _kw_hit(question_text, rule.question_keywords):
            continue
        print(f"[MISCONCEPTION] DB rule matched for topic={topic!r}: {rule.description}")
        return rule.description
    return None


def list_rules(db: Session, subject_id: str) -> list[MisconceptionRule]:
    return (
        db.query(MisconceptionRule)
        .filter(MisconceptionRule.subject_id == subject_id)
        .order_by(MisconceptionRule.topic, MisconceptionRule.created_at)
        .all()
    )


def replace_rules(db: Session, subject_id: str, rules: list[dict], created_by: str) -> int:
    from backend.services import topic_graph_service

    valid_topics = {t["topic"] for t in topic_graph_service.read_graph(db, subject_id)}
    for r in rules:
        if r["topic"] not in valid_topics:
            raise ValueError(f"'{r['topic']}' is not a confirmed topic of this subject.")
        if not (r.get("description") or "").strip():
            raise ValueError("Every misconception rule needs a description.")

    db.query(MisconceptionRule).filter(MisconceptionRule.subject_id == subject_id).delete()
    for r in rules:
        db.add(
            MisconceptionRule(
                subject_id=subject_id,
                topic=r["topic"],
                name=(r.get("name") or None),
                description=r["description"].strip(),
                wrong_answer_keywords=[k.strip() for k in r.get("wrong_answer_keywords", []) if k.strip()],
                question_keywords=[k.strip() for k in r.get("question_keywords", []) if k.strip()],
                created_by=created_by,
            )
        )
    db.commit()
    print(f"[MISCONCEPTION] Stored {len(rules)} rule(s) for subject {subject_id}")
    return len(rules)


_DRAFT_RULES_PROMPT = (
    "You are given a list of topics (with a short gloss). For each topic, list the 1-3 most common "
    "student misconceptions. For each misconception give a short description and the keywords that "
    "would appear in a WRONG multiple-choice answer reflecting it (lowercase, single words or short "
    "phrases).\n\n"
    "Return ONLY a JSON array, no prose. Each item:\n"
    '{{"topic": <the topic name EXACTLY as given, without the gloss>, "name": str, "description": str, '
    '"wrong_answer_keywords": [str], "question_keywords": [str]}}\n\n'
    "Topic names (use these exact strings for \"topic\"):\n{names}\n\n"
    "Glosses for context:\n{glosses}"
)


async def draft_rules_from_topics(db: Session, subject_id: str) -> list[dict]:
    from backend.llm.model_pool import model_pool
    from backend.services import rag_service, topic_graph_service

    graph = topic_graph_service.read_graph(db, subject_id)
    if not graph:
        return []
    names_block = "\n".join(f"- {t['topic']}" for t in graph)
    glosses_block = "\n".join(f"- {t['topic']}: {t['description'] or 'n/a'}" for t in graph)
    prompt = _DRAFT_RULES_PROMPT.format(names=names_block[:4000], glosses=glosses_block[:6000])

    provider, model_idx = model_pool.get_provider()
    raw = ""
    parsed: list[dict] | None = None
    for _ in range(2):
        raw = await provider.generate(prompt, max_tokens=2000)
        try:
            parsed = _extract_json_array_loose(raw)
            break
        except (ValueError, json.JSONDecodeError):
            prompt += "\n\nRespond with ONLY the JSON array."
    if parsed is None:
        raise ValueError("LLM failed to produce a valid misconception-rule list.")

    model_pool.record_usage(model_idx, rag_service.estimate_tokens(prompt) + rag_service.estimate_tokens(raw))

    by_lower = {t["topic"].lower(): t["topic"] for t in graph}
    out: list[dict] = []
    for item in parsed:
        raw_topic = str(item.get("topic", "")).strip()
        desc = str(item.get("description", "")).strip()
        key = raw_topic.split(":")[0].strip().lower()
        topic = by_lower.get(key)
        if topic is None or not desc:
            continue
        out.append(
            {
                "topic": topic,
                "name": (str(item.get("name", "")).strip() or None),
                "description": desc,
                "wrong_answer_keywords": [str(k).strip() for k in item.get("wrong_answer_keywords", []) or []],
                "question_keywords": [str(k).strip() for k in item.get("question_keywords", []) or []],
            }
        )
    print(f"[MISCONCEPTION] drafted {len(out)} rule(s) for subject {subject_id}")
    return out


def _extract_json_array_loose(text: str) -> list[dict]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError("no JSON array found")


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
