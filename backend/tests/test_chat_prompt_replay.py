from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.api import chat
from backend.models.db import SessionMode, SourceType
from backend.services import behavior_service, cache_service, context_service, evidence_service, rag_service


_OLD_STUDY_RULE = "Ask a guiding question first. Do not answer directly."
_ANSWER_FIRST_RULE = "Answer the student's question directly first. Ask at most one optional follow-up question."
_REPLY_DIRECTIVE = "Acknowledge their reply, then explain directly."


class _FakeDb:
    def __init__(self):
        self.session = SimpleNamespace(socratic_state=None)
        self.added = []

    def get(self, _model, _session_id):
        return self.session

    def add(self, value):
        self.added.append(value)

    def commit(self):
        pass

    def refresh(self, _value):
        pass


def _install_prepare_stubs(monkeypatch, history, embedded_texts, cache_lookups):
    db = _FakeDb()
    student_context = {
        "mastery": {},
        "weak_topics": [],
        "strong_topics": [],
        "misconceptions": [],
        "interaction_patterns": {},
        "engagement": {"staleness_flag": False},
        "upcoming_focus": None,
        "latest_educator_note": None,
    }

    monkeypatch.setattr(
        context_service,
        "assemble_class_context",
        lambda *_args: {"subject": "Computer Science", "subject_id": None},
    )
    monkeypatch.setattr(context_service, "assemble_student_context", lambda *_args: student_context)
    monkeypatch.setattr(context_service, "check_prerequisites", lambda *_args: [])
    monkeypatch.setattr(
        context_service,
        "detect_topic",
        lambda message, _subject: "Hadoop" if "hadoop" in message.lower() else None,
    )
    monkeypatch.setattr(chat, "_recent_history", lambda *_args: list(history))
    monkeypatch.setattr(
        "backend.pipeline.embedder.embed_single",
        lambda text, model=None: embedded_texts.append(text) or [float(len(text))],
    )
    monkeypatch.setattr(behavior_service, "get_learning_tag", lambda *_args: None)
    monkeypatch.setattr(cache_service, "compute_context_tier", lambda _context: "strong")
    monkeypatch.setattr(
        cache_service,
        "check_cache",
        lambda *_args: cache_lookups.append(_args[-1]) or None,
    )
    monkeypatch.setattr(rag_service, "retrieve_graph_expanded", lambda *_args, **_kwargs: ([], []))
    monkeypatch.setattr(rag_service, "determine_source_type", lambda _similarity: SourceType.general_knowledge.value)
    return db


def _turn(message, mode=SessionMode.study.value):
    return chat._Turn(
        session_id=uuid4(),
        student_id=uuid4(),
        class_id=str(uuid4()),
        mode=mode,
        message=message,
        topic_override=None,
    )


def _stubbed_llm(prompt):
    if _REPLY_DIRECTIVE in prompt:
        return "HDFS is Hadoop's distributed file system. Replication protects data availability."
    if _OLD_STUDY_RULE in prompt:
        return "Which aspect of Hadoop would you like to explore?"
    return "Hadoop is a distributed computing framework. Which part would you like to explore?"


def test_hadoop_study_replay_builds_direct_prompts_and_preserves_followup_context(monkeypatch):
    history = []
    embedded_texts = []
    cache_lookups = []
    cached_responses = []
    db = _install_prepare_stubs(monkeypatch, history, embedded_texts, cache_lookups)

    monkeypatch.setattr(
        cache_service,
        "store_cache",
        lambda *args: cached_responses.append(args[8]),
    )
    monkeypatch.setattr(evidence_service, "record_interaction", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(evidence_service, "update_engagement", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(behavior_service, "record_turn", lambda *_args, **_kwargs: None)

    failures = []
    first_turn = _turn("tell me about hadoop")
    chat._prepare(db, first_turn, embedding_model=None)
    first_answer = _stubbed_llm(first_turn.prompt)
    chat._finalize(db, first_turn, first_answer, verification_failed=False)

    if _OLD_STUDY_RULE in first_turn.prompt:
        failures.append("first Study prompt still requires a guiding question before answering")
    if _ANSWER_FIRST_RULE not in first_turn.prompt:
        failures.append("first Study prompt lacks answer-first, at-most-one-follow-up guidance")
    if not first_answer.startswith("Hadoop is"):
        failures.append("stubbed first response did not explain Hadoop before asking a follow-up")
    if not cached_responses or not cached_responses[0].startswith("Hadoop is"):
        failures.append("a question-only first response was stored in response_cache")
    if first_turn.cache_eligible is not True or "Student level:" not in first_turn.prompt:
        failures.append("first turn did not follow the expected cache-eligible, generic path")

    history.extend(
        [
            {"role": "user", "content": first_turn.message},
            {"role": "assistant", "content": first_answer},
        ]
    )
    second_turn = _turn("HDFS")
    chat._prepare(db, second_turn, embedding_model=None)
    second_answer = _stubbed_llm(second_turn.prompt)

    if _REPLY_DIRECTIVE not in second_turn.prompt:
        failures.append("follow-up prompt does not acknowledge the reply and explain directly")
    if _OLD_STUDY_RULE in second_turn.prompt:
        failures.append("follow-up prompt still contains the Study guiding-question rule")
    if not second_answer.startswith("HDFS is"):
        failures.append("stubbed follow-up response did not explain HDFS directly")
    if second_turn.query_topic != "Hadoop":
        failures.append("short follow-up did not reuse the Hadoop topic")
    if embedded_texts != ["tell me about hadoop", "tell me about hadoop HDFS"]:
        failures.append(f"retrieval queries did not carry prior context: {embedded_texts!r}")
    if second_turn.cache_eligible is not False or "Student:" not in second_turn.prompt:
        failures.append("later turn did not follow the personalized, cache-ineligible path")
    if cache_lookups != [SessionMode.study.value]:
        failures.append(f"cache lookup was not limited to the first turn: {cache_lookups!r}")

    assert not failures, "\n".join(failures)


@pytest.mark.parametrize(
    "mode",
    [SessionMode.study.value, SessionMode.revision.value, SessionMode.exam_focus.value],
)
def test_question_after_assistant_question_is_capped_in_every_mode(monkeypatch, mode):
    history = [
        {"role": "user", "content": "HDFS"},
        {"role": "assistant", "content": "What do you want to know about HDFS?"},
    ]
    db = _install_prepare_stubs(monkeypatch, history, [], [])
    turn = _turn("Replication", mode=mode)

    chat._prepare(db, turn, embedding_model=None)

    assert _REPLY_DIRECTIVE in turn.prompt
    active_guidance = turn.prompt.split("Active guidance:\n", 1)[1].split("\n\n", 1)[0]
    assert "question" not in active_guidance.lower()
