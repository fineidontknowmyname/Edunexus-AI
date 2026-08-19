import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.api.dependencies import CurrentUser, RequireStudent
from backend.core.database import get_db
from backend.models import schemas
from backend.models.db import ChatMessage, ChatSession, ClassEnrollment, SessionMode
from backend.services import cache_service, context_service, evidence_service, intelligence_service, rag_service

router = APIRouter(prefix="/chat", tags=["chat"])

DbDep = Annotated[Session, Depends(get_db)]

MAX_RESPONSE_TOKENS = 350


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
    db: Session, student_id: str, session_id: str | None, class_id: str, mode: SessionMode, subject: str
) -> ChatSession:
    if session_id:
        session = db.get(ChatSession, session_id)
        if session is None or str(session.student_id) != str(student_id):
            print(f"[CHAT ERROR] session_id={session_id} not found or not owned by student {student_id}")
            raise HTTPException(status_code=404, detail="Chat session not found.")
        session.mode = mode
        db.commit()
        print(f"[CHAT] Reusing session {session.id}, mode set to {mode.value}")
        return session

    session = ChatSession(student_id=student_id, class_id=class_id, subject=subject, mode=mode)
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
    session = _get_or_create_session(
        db, current_user.id, str(payload.session_id) if payload.session_id else None,
        class_id, payload.mode, class_context["subject"],
    )

    async def event_stream():
        student_context = context_service.assemble_student_context(db, current_user.id, class_id)
        query_topic = context_service.detect_topic(payload.message, class_context["subject"])
        prerequisite_gaps = context_service.check_prerequisites(student_context, query_topic, class_context["subject"])

        from backend.main import app
        from backend.pipeline.embedder import embed_single

        embedding_model = getattr(app.state, "embedding_model", None)
        query_vector = embed_single(payload.message, model=embedding_model)

        context_tier = cache_service.compute_context_tier(student_context)
        cached = cache_service.check_cache(db, query_vector, class_context["subject"], context_tier)

        db.add(ChatMessage(session_id=session.id, role="user", content=payload.message))
        db.commit()

        chunk_ids: list = []

        if cached is not None:
            answer_text = cached.response_text
            source_type = cached.source_type.value if cached.source_type else "curriculum"
            chunk_ids = cached.chunk_ids_used or []
            for word in answer_text.split(" "):
                yield _sse({"type": "token", "content": word + " "})
        else:
            chapter_scope = rag_service.taught_chapters_from_syllabus(class_context["syllabus"])
            chunks_with_sim = rag_service.retrieve_chunks(
                db, class_context["subject"], query_vector, chapter_scope=chapter_scope
            )
            top_similarity = chunks_with_sim[0][1] if chunks_with_sim else 0.0
            source_type = rag_service.determine_source_type(top_similarity)
            rules = intelligence_service.apply_rules(
                student_context, query_topic, top_similarity, payload.mode.value, prerequisite_gaps
            )
            history = _recent_history(db, session.id)
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
            print(f"[CHAT] Stream complete — {len(answer_text)} chars generated")

            from backend.llm.model_pool import model_pool

            tokens_used = rag_service.estimate_tokens(prompt) + rag_service.estimate_tokens(answer_text)
            model_pool.record_usage(model_idx, tokens_used)
            print(f"[CHAT] Recorded ~{tokens_used} tokens against model_idx={model_idx}")

            chunk_ids = [chunk.id for chunk, _sim in chunks_with_sim] if source_type == "curriculum" else []
            cache_service.store_cache(
                db, query_vector, class_context["subject"], context_tier, answer_text, chunk_ids, source_type
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
        evidence_service.update_engagement(db, current_user.id)

        print(f"[CHAT SUCCESS] session={session.id} message={assistant_message.id} source_type={source_type} cached={cached is not None}")

        yield _sse({
            "type": "done",
            "session_id": str(session.id),
            "message_id": str(assistant_message.id),
            "source_type": source_type,
            "cached": cached is not None,
            "citations": [str(cid) for cid in (chunk_ids or [])],
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
            "preview": (last_message.content[:60] if last_message else ""),
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
