import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.dependencies import CurrentUser, RequireEducator, RequireStudent
from backend.core.database import get_db
from backend.models import schemas
from backend.models.db import ClassEnrollment, Quiz, QuizAttempt, QuizQuestion, ReviewStatus
from backend.services import evidence_service, progress_service, quiz_service

router = APIRouter(prefix="/quizzes", tags=["quizzes"])

DbDep = Annotated[Session, Depends(get_db)]


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


@router.post("/generate", status_code=201)
async def generate_quiz(
    payload: schemas.QuizGenerateRequest,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    print(f"[QUIZ API] Generate requested by educator={current_user.id} class={payload.class_id}")

    from backend.main import app

    embedding_model = getattr(app.state, "embedding_model", None)
    try:
        quiz = await quiz_service.generate_quiz(
            db=db,
            class_id=str(payload.class_id),
            document_id=str(payload.document_id) if payload.document_id else None,
            unit=payload.unit,
            chapter=payload.chapter,
            title=payload.title,
            created_by_id=current_user.id,
            embedding_model=embedding_model,
            num_questions=payload.num_questions,
        )
    except ValueError as e:
        print(f"[QUIZ API ERROR] Generation failed: {e}")
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
    _educator: Annotated[None, RequireEducator],
):
    quizzes = (
        db.query(Quiz)
        .filter(Quiz.class_id == class_id, Quiz.status == ReviewStatus.pending_review)
        .order_by(Quiz.created_at.desc())
        .all()
    )
    print(f"[QUIZ API] {len(quizzes)} pending quiz(zes) for class={class_id}")
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
    _educator: Annotated[None, RequireEducator],
):
    question = db.get(QuizQuestion, question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found.")
    question.status = payload.status
    db.commit()
    print(f"[QUIZ API] Question {question_id} set to {payload.status.value}")
    return {"id": str(question.id), "status": question.status.value}


@router.post("/{quiz_id}/publish")
def publish_quiz(
    quiz_id: str,
    db: DbDep,
    _educator: Annotated[None, RequireEducator],
):
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found.")
    approved_count = sum(1 for q in quiz.questions if q.status == ReviewStatus.approved)
    if approved_count == 0:
        raise HTTPException(status_code=400, detail="Quiz has no approved questions — approve at least one first.")
    quiz.status = ReviewStatus.approved
    db.commit()
    print(f"[QUIZ API SUCCESS] Quiz {quiz_id} published with {approved_count} approved question(s)")
    return {"id": str(quiz.id), "status": quiz.status.value, "approved_question_count": approved_count}


@router.get("/available")
def list_available(
    class_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
):
    quizzes = (
        db.query(Quiz)
        .filter(Quiz.class_id == class_id, Quiz.status == ReviewStatus.approved)
        .order_by(Quiz.created_at.desc())
        .all()
    )
    print(f"[QUIZ API] {len(quizzes)} available quiz(zes) for student={current_user.id} class={class_id}")
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


@router.get("/{quiz_id}")
def get_quiz(
    quiz_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
):
    quiz = db.get(Quiz, quiz_id)
    if quiz is None or quiz.status != ReviewStatus.approved:
        raise HTTPException(status_code=404, detail="Quiz not found.")
    approved_questions = [q for q in quiz.questions if q.status == ReviewStatus.approved]
    return {
        "id": str(quiz.id),
        "title": quiz.title,
        "questions": [_question_out(q, include_answer=False) for q in approved_questions],
    }


@router.post("/{quiz_id}/attempt", status_code=201)
async def submit_attempt(
    quiz_id: str,
    payload: schemas.QuizAttemptCreate,
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
):
    print(f"[QUIZ API] Attempt submitted by student={current_user.id} quiz={quiz_id}")

    quiz = db.get(Quiz, quiz_id)
    if quiz is None or quiz.status != ReviewStatus.approved:
        raise HTTPException(status_code=404, detail="Quiz not found.")

    enrollment = (
        db.query(ClassEnrollment)
        .filter(ClassEnrollment.student_id == current_user.id, ClassEnrollment.class_id == quiz.class_id)
        .first()
    )
    if enrollment is None:
        raise HTTPException(status_code=403, detail="Not enrolled in this quiz's class.")

    try:
        result = await quiz_service.score_attempt(
            db, quiz, str(current_user.id), str(quiz.class_id), {str(k): v for k, v in payload.answers.items()}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    from datetime import datetime

    attempt = QuizAttempt(
        student_id=current_user.id,
        quiz_id=quiz.id,
        answers=json.dumps(payload.answers),
        topic_scores=json.dumps(result["topic_scores"]),
        score=result["score"],
        completed=True,
        completed_at=datetime.utcnow(),
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    updated_mastery = progress_service.update_mastery_after_attempt(
        db, str(current_user.id), str(quiz.class_id), result["topic_scores"]
    )
    evidence_service.update_engagement(db, current_user.id)

    print(f"[QUIZ API SUCCESS] Attempt {attempt.id} scored {result['score']:.1f}%")

    return {
        "attempt_id": str(attempt.id),
        "score": result["score"],
        "topic_scores": result["topic_scores"],
        "results": result["results"],
        "updated_mastery": updated_mastery,
    }


@router.get("/attempts/mine")
def my_attempts(
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
):
    attempts = (
        db.query(QuizAttempt)
        .filter(QuizAttempt.student_id == current_user.id)
        .order_by(QuizAttempt.completed_at.desc())
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
