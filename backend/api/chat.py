import json
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.api.dependencies import CurrentUser, RequireStudent
from backend.core.database import get_db
from backend.models import schemas
from backend.models.db import ChatMessage, ChatSession, ClassEnrollment, SessionMode
from backend.services import (
    behavior_service,
    cache_service,
    context_service,
    evidence_service,
    intelligence_service,
    rag_service,
    verification_service,
)
from backend.llm.prompts import SOCRATIC_EVAL_PROMPT, SOCRATIC_SYSTEM_PROMPT

router = APIRouter(prefix="/chat", tags=["chat"])

DbDep = Annotated[Session, Depends(get_db)]

MAX_RESPONSE_TOKENS = 350
SOCRATIC_QUESTION_TOKENS = 120

_MARKDOWN_LEADING_PATTERN = re.compile(r"^[#>\-*\s]+", re.MULTILINE)
_MARKDOWN_EMPHASIS_PATTERN = re.compile(r"\*{1,3}|_{1,3}|`+")


def to_preview_text(content: str, max_len: int = 60) -> str:
    plain = _MARKDOWN_LEADING_PATTERN.sub("", content)
    plain = _MARKDOWN_EMPHASIS_PATTERN.sub("", plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain[:max_len]


def _resolve_class_id(db: Session, student_id: str, requested_class_id: str | None) -> str:
    if requested_class_id:
        print(f"[CHAT] Using explicit class_id from request: {requested_class_id}")
        return str(requested_class_id)
    enrollment = db.query(ClassEnrollment).filter(ClassEnrollment.student_id == student_id).first()
    if enrollment is None:
        print(f"[CHAT ERROR] Student {student_id} has no class_id in request and no enrollment on file.")
        raise HTTPException(
            status_code=400,
            detail="Not enrolled in any class. Join one via POST /classes/{class_id}/enroll first.",
        )
    print(f"[CHAT] Resolved class_id from enrollment: {enrollment.class_id}")
    return str(enrollment.class_id)


def _get_or_create_session(
    db: Session,
    student_id: str,
    session_id: str | None,
    class_id: str,
    mode: SessionMode,
    subject: str | None,
    subject_id: str | None,
) -> ChatSession:
    if session_id:
        session = db.get(ChatSession, session_id)
        if session is None or str(session.student_id) != str(student_id):
            print(f"[CHAT ERROR] session_id={session_id} not found or not owned by student {student_id}")
            raise HTTPException(status_code=404, detail="Chat session not found.")
        if session.mode != mode:
            session.socratic_state = None
        session.mode = mode
        db.commit()
        print(f"[CHAT] Reusing session {session.id}, mode set to {mode.value}")
        return session

    session = ChatSession(
        student_id=student_id, class_id=class_id, subject=subject, subject_id=subject_id, mode=mode
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    print(f"[CHAT] Created new session {session.id} (mode={mode.value}, class={class_id})")
    return session


def _recent_history(db: Session, session_id: str) -> list[dict[str, str]]:
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(6)
        .all()
    )
    return [{"role": m.role, "content": m.content} for m in reversed(rows)]


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@router.post("/query")
def chat_query(
    payload: schemas.ChatRequest,
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
):
    print(f"[CHAT] /chat/query — student={current_user.id} mode={payload.mode.value} message={payload.message[:80]!r}")

    class_id = _resolve_class_id(db, current_user.id, str(payload.class_id) if payload.class_id else None)
    class_context = context_service.assemble_class_context(db, class_id)
    subject = class_context["subject"]
    subject_id = class_context["subject_id"]
    session = _get_or_create_session(
        db, current_user.id, str(payload.session_id) if payload.session_id else None,
        class_id, payload.mode, subject, subject_id,
    )

    async def event_stream():
        from backend.llm.model_pool import model_pool
        from backend.main import app
        from backend.pipeline.embedder import embed_single

        student_context = context_service.assemble_student_context(db, current_user.id, class_id)
        embedding_model = getattr(app.state, "embedding_model", None)

        if subject_id:
            query_topic = context_service.detect_topic_for_subject(
                db, payload.message, subject_id, embedding_model
            )
            prerequisite_gaps = context_service.check_prerequisites_for_subject(
                db, student_context, query_topic, subject_id
            )
        else:
            query_topic = context_service.detect_topic(payload.message, subject or "")
            prerequisite_gaps = context_service.check_prerequisites(student_context, query_topic, subject or "")

        query_vector = embed_single(payload.message, model=embedding_model)
        context_tier = cache_service.compute_context_tier(student_context)
        learning_tag = behavior_service.get_learning_tag(db, current_user.id, subject_id, query_topic)

        history = _recent_history(db, session.id)
        last_role = history[-1]["role"] if history else None
        chapter_scope = rag_service.taught_chapters_from_syllabus(class_context["syllabus"])

        db.add(ChatMessage(session_id=session.id, role="user", content=payload.message))
        db.commit()

        is_socratic = payload.mode == SessionMode.socratic and subject_id is not None
        chunk_ids: list = []
        cached = None
        verification_failed = False

        if is_socratic:
            state = json.loads(session.socratic_state) if session.socratic_state else {}
            awaiting = bool(state.get("awaiting_attempt")) and state.get("topic") == query_topic

            chunks_with_sim, contributed = rag_service.retrieve_graph_expanded(
                db, query_vector, query_topic, subject, subject_id, chapter_scope
            )
            top_similarity = chunks_with_sim[0][1] if chunks_with_sim else 0.0
            source_type = rag_service.determine_source_type(top_similarity)
            prompt_chunks = chunks_with_sim if source_type == "curriculum" else []
            rules = intelligence_service.apply_rules(
                student_context, query_topic, top_similarity, "socratic", prerequisite_gaps, learning_tag
            )

            if not awaiting:
                system_prompt = SOCRATIC_SYSTEM_PROMPT
                max_tokens = SOCRATIC_QUESTION_TOKENS
            else:
                system_prompt = SOCRATIC_EVAL_PROMPT
                max_tokens = MAX_RESPONSE_TOKENS

            prompt = rag_service.build_prompt(
                class_context, student_context, rules, prompt_chunks, history, payload.message,
                "socratic", query_topic, system_prompt=system_prompt,
            )
            provider, model_idx = rag_service.get_llm_provider()
            answer_text = ""
            async for token in provider.stream(prompt, max_tokens=max_tokens):
                answer_text += token
                yield _sse({"type": "token", "content": token})
            model_pool.record_usage(
                model_idx, rag_service.estimate_tokens(prompt) + rag_service.estimate_tokens(answer_text)
            )

            if not awaiting:
                session.socratic_state = json.dumps({"topic": query_topic, "awaiting_attempt": True})
                source_type = "curriculum" if prompt_chunks else source_type
                chunk_ids = []
            else:
                session.socratic_state = None
                chunk_ids = [c.id for c, _ in chunks_with_sim] if source_type == "curriculum" else []
            db.commit()

        else:
            cached = cache_service.check_cache(
                db, query_vector, subject, context_tier, subject_id, learning_tag
            )
            if cached is not None:
                answer_text = cached.response_text
                source_type = cached.source_type.value if cached.source_type else "curriculum"
                chunk_ids = cached.chunk_ids_used or []
                for word in answer_text.split(" "):
                    yield _sse({"type": "token", "content": word + " "})
            else:
                chunks_with_sim, contributed = rag_service.retrieve_graph_expanded(
                    db, query_vector, query_topic, subject, subject_id, chapter_scope
                )
                top_similarity = chunks_with_sim[0][1] if chunks_with_sim else 0.0
                source_type = rag_service.determine_source_type(top_similarity)
                rules = intelligence_service.apply_rules(
                    student_context, query_topic, top_similarity, payload.mode.value,
                    prerequisite_gaps, learning_tag,
                )
                prompt_chunks = chunks_with_sim if source_type == "curriculum" else []
                prompt = rag_service.build_prompt(
                    class_context, student_context, rules, prompt_chunks, history, payload.message,
                    payload.mode.value, query_topic,
                )

                provider, model_idx = rag_service.get_llm_provider()
                answer_text = ""
                print("[CHAT] Streaming response from LLM provider...")
                async for token in provider.stream(prompt, max_tokens=MAX_RESPONSE_TOKENS):
                    answer_text += token
                    yield _sse({"type": "token", "content": token})

                model_pool.record_usage(
                    model_idx, rag_service.estimate_tokens(prompt) + rag_service.estimate_tokens(answer_text)
                )

                if verification_service.should_verify(source_type, answer_text, was_cached=False):
                    grounded = await verification_service.verify(
                        answer_text, [c.text for c, _ in prompt_chunks]
                    )
                    if not grounded:
                        verification_failed = True
                        answer_text += verification_service.CAVEAT
                        yield _sse({"type": "token", "content": verification_service.CAVEAT})

                chunk_ids = [c.id for c, _ in chunks_with_sim] if source_type == "curriculum" else []
                cache_service.store_cache(
                    db, query_vector, subject, context_tier, answer_text, chunk_ids, source_type,
                    subject_id=subject_id, learning_tag=learning_tag,
                )

        assistant_message = ChatMessage(
            session_id=session.id,
            role="assistant",
            content=answer_text,
            source_type=source_type,
            chunk_ids_used=chunk_ids or None,
        )
        db.add(assistant_message)
        db.commit()
        db.refresh(assistant_message)

        evidence_service.record_interaction(db, current_user.id, query_topic)
        behavior_service.record_turn(
            db, current_user.id, subject_id, query_topic, payload.message, last_role
        )
        evidence_service.update_engagement(db, current_user.id)

        print(
            f"[CHAT SUCCESS] session={session.id} message={assistant_message.id} "
            f"source_type={source_type} mode={payload.mode.value} cached={cached is not None} "
            f"verify_failed={verification_failed}"
        )

        yield _sse({
            "type": "done",
            "session_id": str(session.id),
            "message_id": str(assistant_message.id),
            "source_type": source_type,
            "cached": cached is not None,
            "citations": [str(cid) for cid in (chunk_ids or [])],
            "verification_failed": verification_failed,
            "learning_tag": learning_tag,
        })

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/sessions")
def list_sessions(
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
):
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.student_id == current_user.id)
        .order_by(ChatSession.created_at.desc())
        .all()
    )
    print(f"[CHAT] Listing {len(sessions)} session(s) for student={current_user.id}")

    result = []
    for session in sessions:
        last_message = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        result.append({
            "session_id": str(session.id),
            "subject": session.subject,
            "mode": session.mode.value,
            "created_at": session.created_at.isoformat(),
            "preview": (to_preview_text(last_message.content) if last_message else ""),
        })
    return result


@router.get("/history")
def chat_history(
    session_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
):
    print(f"[CHAT] History requested for session={session_id} by student={current_user.id}")

    session = db.get(ChatSession, session_id)
    if session is None or str(session.student_id) != str(current_user.id):
        print(f"[CHAT ERROR] History rejected — session {session_id} not found or not owned by {current_user.id}")
        raise HTTPException(status_code=404, detail="Chat session not found.")

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
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
    print(f"[CHAT] Flag requested: message={message_id} by student={current_user.id}")

    message = db.get(ChatMessage, message_id)
    if message is None:
        print(f"[CHAT ERROR] Flag rejected — message {message_id} not found.")
        raise HTTPException(status_code=404, detail="Message not found.")
    session = db.get(ChatSession, message.session_id)
    if session is None or str(session.student_id) != str(current_user.id):
        print(f"[CHAT ERROR] Flag rejected — message {message_id} not owned by student {current_user.id}.")
        raise HTTPException(status_code=404, detail="Message not found.")

    message.flagged_by_student = True
    db.commit()
    print(f"[CHAT SUCCESS] Message {message_id} flagged by student {current_user.id}")
    return {"message": "Flagged for your teacher's review."}
