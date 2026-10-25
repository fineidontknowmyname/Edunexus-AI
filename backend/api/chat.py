import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.api import access
from backend.api.dependencies import CurrentUser, RequireStudent
from backend.core.database import SessionLocal, get_db
from backend.core.rate_limit import rate_limit
from backend.llm.prompts import SOCRATIC_EVAL_PROMPT, SOCRATIC_SYSTEM_PROMPT
from backend.models import schemas
from backend.models.db import ChatMessage, ChatSession, ResponseCache, SessionMode, SourceType
from backend.services import (
    behavior_service,
    cache_service,
    context_service,
    evidence_service,
    intelligence_service,
    misconception_service,
    rag_service,
    topic_graph_service,
    verification_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

DbDep = Annotated[Session, Depends(get_db)]
ChatRateLimit = Depends(rate_limit("chat-query", max_requests=30, window_seconds=60))

MAX_RESPONSE_TOKENS = 600
SOCRATIC_QUESTION_TOKENS = 400
HISTORY_TURNS = 6
STREAM_ERROR_MESSAGE = "The tutor couldn't finish that answer. Please try again in a moment."
PREPARE_ERROR_MESSAGE = "Something went wrong while preparing your answer. Please try again."

_MARKDOWN_LEADING_PATTERN = re.compile(r"^[#>\-*\s]+", re.MULTILINE)
_MARKDOWN_EMPHASIS_PATTERN = re.compile(r"\*{1,3}|_{1,3}|`+")


def to_preview_text(content: str, max_len: int = 60) -> str:
    plain = _MARKDOWN_LEADING_PATTERN.sub("", content)
    plain = _MARKDOWN_EMPHASIS_PATTERN.sub("", plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain[:max_len]


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@dataclass
class _Turn:
    session_id: Any
    student_id: Any
    class_id: str
    mode: str
    message: str
    topic_override: str | None
    subject: str | None = None
    subject_id: str | None = None
    query_topic: str | None = None
    query_vector: list[float] = field(default_factory=list)
    context_tier: str | None = None
    learning_tag: str | None = None
    last_role: str | None = None
    is_socratic: bool = False
    awaiting_attempt: bool = False
    cache_eligible: bool = False
    cached: ResponseCache | None = None
    prompt: str = ""
    max_tokens: int = MAX_RESPONSE_TOKENS
    chunks_with_sim: list = field(default_factory=list)
    prompt_chunks: list = field(default_factory=list)
    source_type: str = SourceType.general_knowledge.value


def _resolve_topic(db: Session, turn: _Turn, embedding_model) -> str | None:
    if turn.topic_override and turn.subject_id:
        confirmed = {t["topic"] for t in topic_graph_service.read_graph(db, turn.subject_id)}
        if turn.topic_override in confirmed:
            return turn.topic_override
    if turn.subject_id:
        return context_service.detect_topic_for_subject(db, turn.message, turn.subject_id, embedding_model)
    return context_service.detect_topic(turn.message, turn.subject or "")


def _recent_history(db: Session, session_id) -> list[dict[str, str]]:
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(HISTORY_TURNS)
        .all()
    )
    return [{"role": m.role, "content": m.content} for m in reversed(rows)]


def _prepare(db: Session, turn: _Turn, embedding_model) -> None:
    from backend.pipeline.embedder import embed_single

    class_context = context_service.assemble_class_context(db, turn.class_id)
    turn.subject = class_context["subject"]
    turn.subject_id = class_context["subject_id"]
    student_context = context_service.assemble_student_context(db, str(turn.student_id), turn.class_id)
    history = _recent_history(db, turn.session_id)
    turn.last_role = history[-1]["role"] if history else None

    session = db.get(ChatSession, turn.session_id)
    stored_topic = None
    if session and session.socratic_state:
        try:
            state_dict = json.loads(session.socratic_state)
            if isinstance(state_dict, dict):
                stored_topic = state_dict.get("topic")
        except (json.JSONDecodeError, TypeError):
            stored_topic = None

    prev_user_msg = next((m["content"] for m in reversed(history) if m["role"] == "user"), None)

    turn.query_topic = _resolve_topic(db, turn, embedding_model)
    is_short_or_topicless = bool(prev_user_msg and (len(turn.message.strip().split()) <= 4 or not turn.query_topic))
    if is_short_or_topicless and not turn.query_topic and stored_topic:
        turn.query_topic = stored_topic

    retrieval_query = f"{prev_user_msg} {turn.message}".strip() if is_short_or_topicless else turn.message
    turn.query_vector = embed_single(retrieval_query, model=embedding_model)

    if turn.subject_id:
        prerequisite_gaps = context_service.check_prerequisites_for_subject(
            db, student_context, turn.query_topic, turn.subject_id
        )
    else:
        prerequisite_gaps = context_service.check_prerequisites(student_context, turn.query_topic, turn.subject or "")

    turn.context_tier = cache_service.compute_context_tier(student_context)
    turn.learning_tag = behavior_service.get_learning_tag(
        db, str(turn.student_id), turn.subject_id, turn.query_topic
    )
    turn.is_socratic = turn.mode == SessionMode.socratic.value and turn.subject_id is not None
    if turn.is_socratic:
        state = json.loads(session.socratic_state) if session.socratic_state else {}
        turn.awaiting_attempt = bool(state.get("awaiting_attempt")) and state.get("topic") == turn.query_topic
    else:
        turn.cache_eligible = not history
        if turn.cache_eligible:
            turn.cached = cache_service.check_cache(
                db, turn.query_vector, turn.class_id, turn.subject_id, turn.context_tier,
                turn.learning_tag, turn.mode,
            )
            if turn.cached is not None:
                return

    turn.chunks_with_sim, _ = rag_service.retrieve_graph_expanded(
        db, turn.query_vector, turn.query_topic, turn.subject, turn.subject_id,
        class_id=turn.class_id,
    )
    top_similarity = turn.chunks_with_sim[0][1] if turn.chunks_with_sim else 0.0
    turn.source_type = rag_service.determine_source_type(top_similarity)
    turn.prompt_chunks = turn.chunks_with_sim if turn.source_type == SourceType.curriculum.value else []

    personalized = not turn.cache_eligible
    rules = intelligence_service.apply_rules(
        student_context, turn.query_topic, top_similarity,
        "socratic" if turn.is_socratic else turn.mode,
        prerequisite_gaps, turn.learning_tag,
        personalized=personalized, context_tier=turn.context_tier,
    )

    last_assistant_msg = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), None)
    assistant_asked_question = bool(last_assistant_msg and last_assistant_msg.strip().endswith("?"))
    if assistant_asked_question:
        rules = [r for r in rules if "question" not in r.lower()]
        rules.append("Acknowledge their reply, then explain directly.")

    system_prompt = rag_service.SYSTEM_PROMPT
    if turn.is_socratic:
        system_prompt = SOCRATIC_EVAL_PROMPT if turn.awaiting_attempt else SOCRATIC_SYSTEM_PROMPT
        turn.max_tokens = MAX_RESPONSE_TOKENS if turn.awaiting_attempt else SOCRATIC_QUESTION_TOKENS

    turn.prompt = rag_service.build_prompt(
        class_context, student_context, rules, turn.prompt_chunks, history, turn.message,
        "socratic" if turn.is_socratic else turn.mode, turn.query_topic,
        system_prompt=system_prompt, personalized=personalized, context_tier=turn.context_tier,
    )


def _finalize(db: Session, turn: _Turn, answer_text: str, verification_failed: bool) -> dict:
    now = datetime.utcnow()
    session = db.get(ChatSession, turn.session_id)

    if turn.cached is not None:
        source_type = turn.cached.source_type.value if turn.cached.source_type else SourceType.curriculum.value
        chunk_ids = list(turn.cached.chunk_ids_used or [])
    else:
        source_type = turn.source_type
        chunk_ids = [c.id for c, _ in turn.chunks_with_sim] if source_type == SourceType.curriculum.value else []

    misconception_resolved = None
    if turn.is_socratic:
        if turn.awaiting_attempt:
            session.socratic_state = None
            if turn.query_topic and misconception_service.resolve_misconceptions_for_topic(
                db, str(turn.student_id), turn.class_id, turn.query_topic, "completed a guided Socratic session"
            ):
                misconception_resolved = turn.query_topic
        else:
            session.socratic_state = json.dumps({"topic": turn.query_topic, "awaiting_attempt": True})
            chunk_ids = []
    elif turn.query_topic:
        session.socratic_state = json.dumps({"topic": turn.query_topic})

    db.add(ChatMessage(session_id=turn.session_id, role="user", content=turn.message, created_at=now))
    assistant = ChatMessage(
        session_id=turn.session_id,
        role="assistant",
        content=answer_text,
        source_type=source_type,
        chunk_ids_used=chunk_ids or None,
        created_at=now + timedelta(milliseconds=1),
    )
    db.add(assistant)
    db.commit()
    db.refresh(assistant)

    if turn.cache_eligible and turn.cached is None and not verification_failed:
        cache_service.store_cache(
            db, turn.query_vector, turn.class_id, turn.subject, turn.subject_id, turn.context_tier,
            turn.learning_tag, turn.mode, answer_text, chunk_ids, source_type,
        )

    evidence_service.record_interaction(
        db, str(turn.student_id), turn.query_topic, class_id=turn.class_id, subject_id=turn.subject_id
    )
    behavior_service.record_turn(
        db, str(turn.student_id), turn.subject_id, turn.query_topic, turn.message, turn.last_role
    )
    evidence_service.update_engagement(db, turn.student_id)

    return {
        "message_id": str(assistant.id),
        "source_type": source_type,
        "citations": [str(cid) for cid in chunk_ids],
        "misconception_resolved": misconception_resolved,
    }


def _session_for_request(db: Session, payload: schemas.ChatRequest, student) -> ChatSession:
    mode = payload.mode
    if payload.session_id:
        session = db.get(ChatSession, access.parse_uuid(payload.session_id, "Chat session"))
        if session is None or session.student_id != student.id:
            raise HTTPException(status_code=404, detail="Chat session not found.")
        if session.class_id is None:
            session.class_id = access.student_class_id(db, student, payload.class_id)
        elif not access.is_enrolled(db, session.class_id, student.id):
            raise HTTPException(status_code=404, detail="Chat session not found.")
        if session.mode != mode:
            session.socratic_state = None
        session.mode = mode
        db.commit()
        return session

    class_id = access.student_class_id(db, student, payload.class_id)
    class_context = context_service.assemble_class_context(db, class_id)
    session = ChatSession(
        student_id=student.id,
        class_id=class_id,
        subject=class_context["subject"],
        subject_id=class_context["subject_id"],
        mode=mode,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.post("/query", dependencies=[ChatRateLimit])
def chat_query(
    payload: schemas.ChatRequest,
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
):
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message can't be empty.")

    session = _session_for_request(db, payload, current_user)
    turn = _Turn(
        session_id=session.id,
        student_id=current_user.id,
        class_id=str(session.class_id),
        mode=payload.mode.value,
        message=message,
        topic_override=(payload.topic or "").strip() or None,
    )

    from backend.main import app

    embedding_model = getattr(app.state, "embedding_model", None)

    async def event_stream():
        from backend.llm.model_pool import model_pool

        stream_db = SessionLocal()
        try:
            try:
                await run_in_threadpool(_prepare, stream_db, turn, embedding_model)
            except Exception:  # noqa: BLE001
                logger.exception("Chat preparation failed for session %s", turn.session_id)
                stream_db.rollback()
                yield _sse({"type": "error", "detail": PREPARE_ERROR_MESSAGE})
                return

            answer_text = ""
            verification_failed = False
            if turn.cached is not None:
                answer_text = turn.cached.response_text
                for word in answer_text.split(" "):
                    yield _sse({"type": "token", "content": word + " "})
            else:
                provider, model_idx = rag_service.get_llm_provider()
                try:
                    async for token in provider.stream(turn.prompt, max_tokens=turn.max_tokens):
                        answer_text += token
                        yield _sse({"type": "token", "content": token})
                except Exception:  # noqa: BLE001
                    logger.exception("LLM stream failed for session %s", turn.session_id)
                    yield _sse({"type": "error", "detail": STREAM_ERROR_MESSAGE})
                    return
                if not answer_text.strip():
                    yield _sse({"type": "error", "detail": STREAM_ERROR_MESSAGE})
                    return
                model_pool.record_usage(
                    model_idx, rag_service.estimate_tokens(turn.prompt) + rag_service.estimate_tokens(answer_text)
                )
                if not turn.is_socratic and verification_service.should_verify(
                    turn.source_type, answer_text, was_cached=False
                ):
                    grounded = await verification_service.verify(answer_text, [c.text for c, _ in turn.prompt_chunks])
                    if not grounded:
                        verification_failed = True
                        answer_text += verification_service.CAVEAT
                        yield _sse({"type": "token", "content": verification_service.CAVEAT})

            try:
                saved = await run_in_threadpool(_finalize, stream_db, turn, answer_text, verification_failed)
            except Exception:  # noqa: BLE001
                logger.exception("Saving chat turn failed for session %s", turn.session_id)
                stream_db.rollback()
                yield _sse({"type": "error", "detail": "Your answer was generated but couldn't be saved. Please try again."})
                return

            yield _sse({
                "type": "done",
                "session_id": str(turn.session_id),
                "message_id": saved["message_id"],
                "source_type": saved["source_type"],
                "cached": turn.cached is not None,
                "citations": saved["citations"],
                "verification_failed": verification_failed,
                "learning_tag": turn.learning_tag,
                "misconception_resolved": saved["misconception_resolved"],
            })
        finally:
            stream_db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.get("/sessions")
def list_sessions(
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
    limit: int = 50,
    offset: int = 0,
):
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.student_id == current_user.id)
        .order_by(ChatSession.created_at.desc())
        .limit(max(1, min(limit, 100)))
        .offset(max(0, offset))
        .all()
    )
    ids = [s.id for s in sessions]
    previews = {}
    if ids:
        rows = (
            db.query(ChatMessage.session_id, ChatMessage.content)
            .filter(ChatMessage.session_id.in_(ids))
            .distinct(ChatMessage.session_id)
            .order_by(ChatMessage.session_id, ChatMessage.created_at.desc())
            .all()
        )
        previews = {row.session_id: row.content for row in rows}
    return [
        {
            "session_id": str(session.id),
            "subject": session.subject,
            "mode": session.mode.value,
            "created_at": session.created_at.isoformat(),
            "preview": to_preview_text(previews[session.id]) if session.id in previews else "",
        }
        for session in sessions
    ]


@router.get("/history")
def chat_history(
    session_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
    limit: int = 200,
):
    session = db.get(ChatSession, access.parse_uuid(session_id, "Chat session"))
    if session is None or session.student_id != current_user.id:
        raise HTTPException(status_code=404, detail="Chat session not found.")

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
    messages.reverse()
    return {
        "session_id": str(session.id),
        "mode": session.mode.value,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "source_type": m.source_type.value if m.source_type else None,
                "flagged_by_student": m.flagged_by_student,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
    }


@router.patch("/messages/{message_id}/flag")
def flag_message(
    message_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
):
    message = db.get(ChatMessage, access.parse_uuid(message_id, "Message"))
    session = db.get(ChatSession, message.session_id) if message else None
    if message is None or session is None or session.student_id != current_user.id:
        raise HTTPException(status_code=404, detail="Message not found.")
    message.flagged_by_student = True
    db.commit()
    return {"message": "Flagged for your teacher's review."}
