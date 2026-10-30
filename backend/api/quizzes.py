import json
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api import access
from backend.api.dependencies import CurrentUser, RequireEducator, RequireStudent
from backend.core.database import get_db
from backend.core.rate_limit import rate_limit
from backend.models import schemas
from backend.models.db import Quiz, QuizAttempt, QuizAttemptAnswer, QuizQuestion, ReviewStatus, User
from backend.services import evidence_service, progress_service, quiz_service

router = APIRouter(prefix="/quizzes", tags=["quizzes"])

DbDep = Annotated[Session, Depends(get_db)]
GenerateRateLimit = Depends(rate_limit("quiz-generate", max_requests=6, window_seconds=600))
DUPLICATE_WINDOW = timedelta(seconds=30)


def _question_out(q: QuizQuestion, include_answer: bool) -> dict:
    out = {
        "id": str(q.id),
        "question_text": q.question_text,
        "options": json.loads(q.options),
        "topic": q.topic,
        "difficulty": q.difficulty.value,
        "status": q.status.value,
    }
    if include_answer:
        out["correct_answer"] = q.correct_answer
    return out


@router.post("/generate", status_code=201, dependencies=[GenerateRateLimit])
async def generate_quiz(
    payload: schemas.QuizGenerateRequest,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    class_row = access.owned_class(db, payload.class_id, current_user)
    if payload.document_id:
        doc = access.owned_document(db, payload.document_id, current_user)
        if doc.class_id != class_row.id:
            raise HTTPException(status_code=400, detail="That document belongs to a different class.")

    from backend.main import app

    embedding_model = getattr(app.state, "embedding_model", None)
    try:
        quiz = await quiz_service.generate_quiz(
            db=db,
            class_id=str(class_row.id),
            document_id=str(payload.document_id) if payload.document_id else None,
            unit=payload.unit,
            chapter=payload.chapter,
            title=payload.title,
            created_by_id=current_user.id,
            embedding_model=embedding_model,
            num_questions=payload.num_questions,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "quiz_id": str(quiz.id),
        "title": quiz.title,
        "question_count": len(quiz.questions),
        "status": quiz.status.value,
    }


@router.get("/pending")
def list_pending(
    class_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    class_row = access.owned_class(db, class_id, current_user)
    quizzes = (
        db.query(Quiz)
        .filter(Quiz.class_id == class_row.id, Quiz.status == ReviewStatus.pending_review)
        .order_by(Quiz.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(q.id),
            "title": q.title,
            "unit": q.unit,
            "chapter": q.chapter,
            "status": q.status.value,
            "created_at": q.created_at.isoformat(),
            "questions": [_question_out(question, include_answer=True) for question in q.questions],
        }
        for q in quizzes
    ]


@router.patch("/questions/{question_id}")
def update_question_status(
    question_id: str,
    payload: schemas.QuestionStatusUpdate,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    question = access.owned_question(db, question_id, current_user)
    question.status = payload.status
    db.commit()
    return {"id": str(question.id), "status": question.status.value}


@router.post("/{quiz_id}/publish")
def publish_quiz(
    quiz_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    quiz = access.owned_quiz(db, quiz_id, current_user)
    approved_count = sum(1 for q in quiz.questions if q.status == ReviewStatus.approved)
    if approved_count == 0:
        raise HTTPException(status_code=400, detail="Quiz has no approved questions. Approve at least one first.")
    quiz.status = ReviewStatus.approved
    db.commit()
    return {"id": str(quiz.id), "status": quiz.status.value, "approved_question_count": approved_count}


@router.get("/available")
def list_available(
    class_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
):
    class_row = access.enrolled_class(db, class_id, current_user)
    quizzes = (
        db.query(Quiz)
        .filter(Quiz.class_id == class_row.id, Quiz.status == ReviewStatus.approved)
        .order_by(Quiz.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(q.id),
            "title": q.title,
            "unit": q.unit,
            "chapter": q.chapter,
            "question_count": sum(1 for question in q.questions if question.status == ReviewStatus.approved),
        }
        for q in quizzes
    ]


@router.get("/attempts/mine")
def my_attempts(
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
    limit: int = 100,
):
    attempts = (
        db.query(QuizAttempt)
        .filter(QuizAttempt.student_id == current_user.id, QuizAttempt.completed == True)  # noqa: E712
        .order_by(QuizAttempt.completed_at.desc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return [
        {
            "id": str(a.id),
            "quiz_id": str(a.quiz_id),
            "score": a.score,
            "topic_scores": json.loads(a.topic_scores) if a.topic_scores else {},
            "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        }
        for a in attempts
    ]


@router.get("/{quiz_id}")
def get_quiz(
    quiz_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
):
    quiz = access.enrolled_quiz(db, quiz_id, current_user)
    available_questions = quiz_service.available_questions_for_student(
        db, quiz, str(current_user.id), str(quiz.class_id)
    )
    return {
        "id": str(quiz.id),
        "title": quiz.title,
        "questions": [_question_out(q, include_answer=False) for q in available_questions],
    }


def _claim_submission(db: Session, quiz: Quiz, student: User, answers_json: str) -> QuizAttempt:
    db.query(User).filter(User.id == student.id).with_for_update().one()
    recent = (
        db.query(QuizAttempt)
        .filter(
            QuizAttempt.student_id == student.id,
            QuizAttempt.quiz_id == quiz.id,
            QuizAttempt.answers == answers_json,
            QuizAttempt.started_at >= datetime.utcnow() - DUPLICATE_WINDOW,
        )
        .first()
    )
    if recent is not None:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This quiz submission was already received. Check your results before submitting again.",
        )
    attempt = QuizAttempt(student_id=student.id, quiz_id=quiz.id, answers=answers_json, completed=False)
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


@router.post("/{quiz_id}/attempt", status_code=201)
async def submit_attempt(
    quiz_id: str,
    payload: schemas.QuizAttemptCreate,
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
):
    quiz = access.enrolled_quiz(db, quiz_id, current_user)
    answers = {str(k): v for k, v in payload.answers.items()}
    answers_json = json.dumps(answers, sort_keys=True)
    attempt = _claim_submission(db, quiz, current_user, answers_json)

    try:
        result = await quiz_service.score_attempt(
            db, quiz, str(current_user.id), str(quiz.class_id), answers, source_attempt_id=str(attempt.id)
        )
    except ValueError as e:
        db.rollback()
        db.delete(db.get(QuizAttempt, attempt.id))
        db.commit()
        raise HTTPException(status_code=400, detail=str(e))

    attempt = db.get(QuizAttempt, attempt.id)
    attempt.topic_scores = json.dumps(result["topic_scores"])
    attempt.score = result["score"]
    attempt.completed = True
    attempt.completed_at = datetime.utcnow()
    db.commit()

    try:
        with db.begin_nested():
            answer_rows = quiz_service.build_answer_rows(
                attempt_id=str(attempt.id),
                student_id=str(current_user.id),
                results=result["results"],
                answered_at=attempt.completed_at,
                class_id=str(quiz.class_id),
            )
            for row in answer_rows:
                db.add(QuizAttemptAnswer(**row))
            db.flush()
    except Exception as exc:
        print(f"[QUIZ WARNING] Failed to persist per-question answers for attempt {attempt.id}: {exc}")

    updated_mastery = progress_service.update_mastery_after_attempt(
        db, str(current_user.id), str(quiz.class_id), result["topic_scores"],
        topic_passed=result.get("topic_passed"),
    )
    evidence_service.update_engagement(db, current_user.id)

    try:
        from backend.services import recommendation_service
        recommendation_service.link_quiz_attempt_to_recommendations(
            db,
            student_id=str(current_user.id),
            class_id=str(quiz.class_id),
            attempt_id=str(attempt.id),
            topic_scores=result["topic_scores"],
            updated_mastery=updated_mastery,
        )
    except Exception as exc:
        print(f"[QUIZ WARNING] Failed to link attempt to recommendations: {exc}")

    from backend.core.config import get_settings

    if get_settings().mastery_v2_enabled:
        try:
            v2_out = progress_service.update_mastery_v2_after_attempt(
                db, str(current_user.id), result["topic_scores"], class_id=str(quiz.class_id)
            )
            for topic_name, v2_data in v2_out.items():
                if topic_name in updated_mastery:
                    updated_mastery[topic_name]["mastery_v2"] = v2_data
        except Exception as exc:
            print(f"[QUIZ WARNING] Failed to compute mastery v2 for student {current_user.id}: {exc}")

    return {
        "attempt_id": str(attempt.id),
        "score": result["score"],
        "topic_scores": result["topic_scores"],
        "results": result["results"],
        "updated_mastery": updated_mastery,
    }
