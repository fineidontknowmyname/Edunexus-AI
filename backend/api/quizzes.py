import json
import uuid
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.api import access
from backend.api.dependencies import CurrentUser, RequireEducator, RequireStudent
from backend.core.database import get_db
from backend.core.rate_limit import rate_limit
from backend.models import schemas
from backend.models.db import (
    QuestionReport,
    Quiz,
    QuizAttempt,
    QuizAttemptAnswer,
    QuizQuestion,
    ReviewStatus,
    TopicMastery,
    User,
    UserRole,
)
from backend.services import coverage_service, evidence_service, progress_service, quiz_service

router = APIRouter(prefix="/quizzes", tags=["quizzes"])

DbDep = Annotated[Session, Depends(get_db)]
GenerateRateLimit = Depends(rate_limit("quiz-generate", max_requests=6, window_seconds=600))
TopicQuizRateLimit = Depends(rate_limit("topic-quiz-generate", max_requests=10, window_seconds=300))
DUPLICATE_WINDOW = timedelta(seconds=30)


def _question_out(q: QuizQuestion, include_answer: bool) -> dict:
    try:
        options = json.loads(q.options) if q.options else []
    except Exception:
        options = [q.options] if q.options else []

    out: dict[str, Any] = {
        "id": str(q.id),
        "question_text": q.question_text,
        "options": options,
        "topic": q.topic,
        "difficulty": q.difficulty.value if hasattr(q.difficulty, "value") else str(q.difficulty),
        "status": q.status.value if hasattr(q.status, "value") else str(q.status),
        "question_type": getattr(q, "question_type", "single_choice") or "single_choice",
        "question_order": getattr(q, "question_order", 1) or 1,
        "points": getattr(q, "points", 1.0) or 1.0,
        "partial_credit_allowed": bool(getattr(q, "partial_credit_allowed", False)),
        "source_document_id": str(q.source_document_id) if getattr(q, "source_document_id", None) else None,
        "source_page_number": getattr(q, "source_page_number", None),
    }
    if include_answer:
        if q.correct_answer and str(q.correct_answer).startswith("["):
            try:
                out["correct_answer"] = json.loads(q.correct_answer)
            except Exception:
                out["correct_answer"] = q.correct_answer
        else:
            out["correct_answer"] = q.correct_answer
        out["explanation"] = q.explanation
        provenance = None
        if getattr(q, "generation_meta", None):
            try:
                provenance = json.loads(q.generation_meta)
            except Exception:
                provenance = None
        out["provenance"] = provenance
    return out


# --- FACULTY QUIZ MANAGEMENT ENDPOINTS ---


@router.post("", response_model=schemas.QuizRead, status_code=201)
def create_quiz(
    payload: schemas.QuizCreate,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    """Faculty creates a new draft or standard quiz."""
    class_row = access.owned_class(db, payload.class_id, current_user)
    doc_id = None
    if payload.document_id:
        doc = access.owned_document(db, payload.document_id, current_user)
        doc_id = str(doc.id)

    quiz = quiz_service.create_manual_quiz(
        db=db,
        class_id=str(class_row.id),
        title=payload.title,
        created_by_id=current_user.id,
        description=payload.description,
        unit=payload.unit,
        chapter=payload.chapter,
        document_id=doc_id,
        time_limit_minutes=payload.time_limit_minutes,
        passing_percentage=payload.passing_percentage,
        status=payload.status or ReviewStatus.draft,
    )
    return quiz


@router.get("")
def list_quizzes_faculty(
    class_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
    status_filter: str | None = None,
):
    """Faculty lists all quizzes for a class with optional status filtering."""
    class_row = access.owned_class(db, class_id, current_user)
    query = db.query(Quiz).filter(Quiz.class_id == class_row.id)
    if status_filter:
        try:
            st = ReviewStatus(status_filter)
            query = query.filter(Quiz.status == st)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid quiz status '{status_filter}'.")

    quizzes = query.order_by(Quiz.created_at.desc()).all()
    return [
        {
            "id": str(q.id),
            "title": q.title,
            "description": q.description,
            "unit": q.unit,
            "chapter": q.chapter,
            "generation_type": q.generation_type,
            "status": q.status.value,
            "version": q.version,
            "time_limit_minutes": q.time_limit_minutes,
            "passing_percentage": q.passing_percentage,
            "question_count": len(q.questions),
            "created_at": q.created_at.isoformat(),
            "updated_at": q.updated_at.isoformat() if q.updated_at else None,
        }
        for q in quizzes
    ]


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
        "requested_count": getattr(quiz, "_requested_count", payload.num_questions),
        "rejected_count": getattr(quiz, "_rejected_count", 0),
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
            "generation_type": q.generation_type,
            "status": q.status.value,
            "created_at": q.created_at.isoformat(),
            "questions": [_question_out(question, include_answer=True) for question in q.questions],
        }
        for q in quizzes
    ]


@router.get("/available")
def list_available(
    class_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
):
    """Students list approved quizzes only (drafts and archived are isolated)."""
    class_row = access.enrolled_class(db, class_id, current_user)
    quizzes = (
        db.query(Quiz)
        .filter(
            Quiz.class_id == class_row.id,
            Quiz.status == ReviewStatus.approved,
            Quiz.generation_type != "topic_practice",
        )
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


@router.post("/topic-quiz", response_model=schemas.TopicQuizResponse, status_code=201, dependencies=[TopicQuizRateLimit])
async def generate_topic_quiz_endpoint(
    payload: schemas.TopicQuizRequest,
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
):
    """Students request an on-demand diagnostic practice quiz scoped strictly to a weak or target curriculum topic."""
    class_row = access.enrolled_class(db, payload.class_id, current_user)

    from backend.main import app

    embedding_model = getattr(app.state, "embedding_model", None)

    try:
        quiz = await quiz_service.generate_topic_quiz(
            db=db,
            class_id=str(class_row.id),
            topic=payload.topic,
            topic_id=str(payload.topic_id) if payload.topic_id else None,
            student_user=current_user,
            embedding_model=embedding_model,
            num_questions=payload.num_questions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "quiz_id": quiz.id,
        "title": quiz.title,
        "topic": payload.topic,
        "question_count": len(quiz.questions),
        "status": quiz.status,
    }


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
            "quiz_title": a.quiz.title if a.quiz else "Quiz",
            "quiz_version": a.quiz_version,
            "score": a.score,
            "topic_scores": json.loads(a.topic_scores) if a.topic_scores else {},
            "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        }
        for a in attempts
    ]


@router.get("/attempts/{attempt_id}")
def get_attempt_detail(
    attempt_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
):
    """Student retrieves question-level results and answers for their completed attempt."""
    try:
        att_uuid = uuid.UUID(attempt_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid attempt ID.")

    attempt = (
        db.query(QuizAttempt)
        .filter(QuizAttempt.id == att_uuid, QuizAttempt.student_id == current_user.id)
        .first()
    )
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found.")

    answers = (
        db.query(QuizAttemptAnswer)
        .filter(QuizAttemptAnswer.attempt_id == attempt.id)
        .all()
    )

    quiz_questions = {str(q.id): q for q in (attempt.quiz.questions if attempt.quiz else [])}
    results = []

    if answers:
        for ans in answers:
            qid_str = str(ans.question_id)
            qq = quiz_questions.get(qid_str)
            raw_ca = qq.correct_answer if qq else ""
            try:
                parsed_ca = json.loads(raw_ca) if isinstance(raw_ca, str) and raw_ca.strip().startswith("[") else raw_ca
            except Exception:
                parsed_ca = raw_ca

            raw_chosen = ans.selected_options
            if raw_chosen is None and qq:
                try:
                    att_answers = json.loads(attempt.answers) if attempt.answers else {}
                    raw_chosen = att_answers.get(qid_str)
                except Exception:
                    raw_chosen = None
            try:
                parsed_chosen = json.loads(raw_chosen) if isinstance(raw_chosen, str) and raw_chosen.strip().startswith("[") else raw_chosen
            except Exception:
                parsed_chosen = raw_chosen

            points_pos = float(ans.points_possible) if ans.points_possible is not None else (float(qq.points) if qq and qq.points is not None else 1.0)
            earned_pts = float(ans.earned_points) if ans.earned_points is not None else (points_pos if ans.is_correct else 0.0)

            results.append({
                "question_id": qid_str,
                "correct": bool(ans.is_correct),
                "correct_answer": parsed_ca,
                "chosen": parsed_chosen,
                "points_possible": points_pos,
                "earned_points": earned_pts,
                "question_type": qq.question_type.value if qq and hasattr(qq.question_type, "value") else (str(qq.question_type) if qq else "multiple_choice"),
                "explanation": qq.explanation if qq else None,
                "topic": ans.topic,
            })
    else:
        try:
            att_answers = json.loads(attempt.answers) if attempt.answers else {}
        except Exception:
            att_answers = {}
        for qid_str, chosen_val in att_answers.items():
            qq = quiz_questions.get(qid_str)
            raw_ca = qq.correct_answer if qq else ""
            try:
                parsed_ca = json.loads(raw_ca) if isinstance(raw_ca, str) and raw_ca.strip().startswith("[") else raw_ca
            except Exception:
                parsed_ca = raw_ca
            try:
                parsed_chosen = json.loads(chosen_val) if isinstance(chosen_val, str) and chosen_val.strip().startswith("[") else chosen_val
            except Exception:
                parsed_chosen = chosen_val

            is_corr = str(parsed_chosen).strip().lower() == str(parsed_ca).strip().lower() if parsed_ca else False
            points_pos = float(qq.points) if qq and qq.points is not None else 1.0
            earned_pts = points_pos if is_corr else 0.0

            results.append({
                "question_id": qid_str,
                "correct": is_corr,
                "correct_answer": parsed_ca,
                "chosen": parsed_chosen,
                "points_possible": points_pos,
                "earned_points": earned_pts,
                "question_type": qq.question_type.value if qq and hasattr(qq.question_type, "value") else (str(qq.question_type) if qq else "multiple_choice"),
                "explanation": qq.explanation if qq else None,
                "topic": qq.topic if qq else None,
            })

    updated_mastery = {}
    if attempt.quiz and attempt.quiz.class_id:
        masteries = (
            db.query(TopicMastery)
            .filter(TopicMastery.student_id == current_user.id, TopicMastery.class_id == attempt.quiz.class_id)
            .all()
        )
        for m in masteries:
            updated_mastery[m.topic] = {
                "mastery_score": m.mastery_score,
                "trend": m.trend.value if hasattr(m.trend, "value") else str(m.trend),
                "attempt_count": m.attempt_count,
            }

    quiz_detail = None
    if attempt.quiz:
        quiz_detail = {
            "id": str(attempt.quiz.id),
            "title": attempt.quiz.title,
            "class_id": str(attempt.quiz.class_id) if attempt.quiz.class_id else None,
            "questions": [
                _question_out(q, include_answer=True)
                for q in sorted(attempt.quiz.questions, key=lambda x: (x.question_order or 0, str(x.id)))
            ],
        }

    return {
        "id": str(attempt.id),
        "attempt_id": str(attempt.id),
        "quiz_id": str(attempt.quiz_id),
        "class_id": str(attempt.quiz.class_id) if attempt.quiz and attempt.quiz.class_id else None,
        "quiz_title": attempt.quiz.title if attempt.quiz else "Quiz",
        "quiz_version": attempt.quiz_version,
        "score": attempt.score,
        "topic_scores": json.loads(attempt.topic_scores) if attempt.topic_scores else {},
        "completed": attempt.completed,
        "completed_at": attempt.completed_at.isoformat() if attempt.completed_at else None,
        "answers": [
            {
                "question_id": str(ans.question_id),
                "topic": ans.topic,
                "is_correct": ans.is_correct,
                "difficulty": ans.difficulty,
            }
            for ans in answers
        ],
        "results": results,
        "quiz": quiz_detail,
        "updated_mastery": updated_mastery,
    }


# --- QUESTION LEVEL OPERATIONS (Declared before parameterized {quiz_id}) ---


@router.get("/questions/{question_id}")
def get_question_endpoint(
    question_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    """Faculty retrieves a single question's complete authoring details."""
    question = access.owned_question(db, question_id, current_user)
    out = _question_out(question, include_answer=True)
    out.update({
        "question_type": question.question_type,
        "question_order": question.question_order,
        "points": question.points,
        "explanation": question.explanation,
        "partial_credit_allowed": question.partial_credit_allowed,
        "topic_id": str(question.topic_id) if question.topic_id else None,
        "source_document_id": str(question.source_document_id) if question.source_document_id else None,
        "source_page_number": question.source_page_number,
        "version": question.version,
    })
    return out


@router.put("/questions/{question_id}")
def update_question_endpoint(
    question_id: str,
    payload: schemas.QuizQuestionUpdate,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    """Faculty updates question content, options, correct answer, points, type, or curriculum mapping."""
    question = access.owned_question(db, question_id, current_user)
    try:
        updated = quiz_service.update_question(
            db, question, payload.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _question_out(updated, include_answer=True)


@router.delete("/questions/{question_id}")
def delete_question_endpoint(
    question_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    """Faculty safely deletes a question (blocked if student attempts exist)."""
    question = access.owned_question(db, question_id, current_user)
    try:
        quiz_service.delete_question(db, question)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"message": "Question deleted successfully."}


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


@router.post("/questions/{question_id}/report", response_model=schemas.QuestionFeedbackResponse, status_code=201)
def report_question(
    question_id: str,
    payload: schemas.QuestionFeedbackCreate,
    db: DbDep,
    current_user: CurrentUser,
):
    """
    Students and faculty can report inaccuracies, ambiguities, or technical errors
    on generated questions to ensure continuous evaluation, academic oversight, and defect logging.
    """
    q_uuid = access.parse_uuid(question_id, "Question")
    question = db.get(QuizQuestion, q_uuid)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found.")

    quiz = question.quiz
    if not quiz:
        raise HTTPException(status_code=404, detail="Parent quiz not found.")

    # Validate access: enrolled student or class educator
    if current_user.role == UserRole.student:
        access.enrolled_quiz(db, quiz.id, current_user)
    elif current_user.role in (UserRole.educator, UserRole.admin):
        access.owned_quiz(db, quiz.id, current_user)

    role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)

    # Upsert pattern handling unique constraint (question_id, reporter_id, category)
    existing = (
        db.query(QuestionReport)
        .filter(
            QuestionReport.question_id == question.id,
            QuestionReport.reporter_id == current_user.id,
            QuestionReport.category == payload.category,
        )
        .first()
    )
    if existing:
        existing.comment = payload.comment
        existing.created_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        report_row = existing
    else:
        report_row = QuestionReport(
            question_id=question.id,
            quiz_id=quiz.id,
            class_id=quiz.class_id,
            reporter_id=current_user.id,
            reporter_role=role_str,
            category=payload.category,
            comment=payload.comment,
            created_at=datetime.utcnow(),
        )
        db.add(report_row)
        try:
            db.commit()
            db.refresh(report_row)
        except IntegrityError:
            db.rollback()
            existing = (
                db.query(QuestionReport)
                .filter(
                    QuestionReport.question_id == question.id,
                    QuestionReport.reporter_id == current_user.id,
                    QuestionReport.category == payload.category,
                )
                .first()
            )
            if existing:
                existing.comment = payload.comment
                existing.created_at = datetime.utcnow()
                db.commit()
                db.refresh(existing)
                report_row = existing
            else:
                raise

    return schemas.QuestionFeedbackResponse(
        report_id=str(report_row.id),
        question_id=str(question.id),
        quiz_id=str(quiz.id),
        category=report_row.category,
        topic=question.topic,
        status="received",
        created_at=report_row.created_at.isoformat() if report_row.created_at else datetime.utcnow().isoformat(),
        message="Feedback received and logged for academic review.",
    )


@router.get("/questions/{question_id}/reports", response_model=list[schemas.QuestionReportItem])
def get_question_reports(
    question_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    """Educators retrieve academic audit reports on a question (reporter identities strictly redacted)."""
    question = access.owned_question(db, question_id, current_user)
    reports = (
        db.query(QuestionReport)
        .filter(QuestionReport.question_id == question.id)
        .order_by(QuestionReport.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": str(r.id),
            "category": r.category,
            "comment": r.comment,
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "reporter_role": r.reporter_role or "student",
        }
        for r in reports
    ]


@router.post("/questions/{question_id}/regenerate", dependencies=[GenerateRateLimit])
async def regenerate_question_endpoint(
    question_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    """Faculty regenerates a single pending or rejected question using its source grounding."""
    question = access.owned_question(db, question_id, current_user)

    from backend.main import app

    embedding_model = getattr(app.state, "embedding_model", None)

    try:
        updated = await quiz_service.regenerate_question(db, question, embedding_model=embedding_model)
    except ValueError as exc:
        msg = str(exc)
        if (
            "Only pending or rejected" in msg
            or "already has student answers" in msg
            or "No source material" in msg
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
        elif "Failed to generate" in msg or "validation" in msg.lower() or "candidate" in msg.lower():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    return _question_out(updated, include_answer=True)


# --- SPECIFIC QUIZ DETAIL & ACTIONS ---


@router.get("/{quiz_id}/faculty")
def get_quiz_faculty(
    quiz_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    """Faculty retrieves detailed quiz structure including questions, answers, points, and mappings."""
    quiz = access.owned_quiz(db, quiz_id, current_user)
    quiz_q_ids = [q.id for q in quiz.questions]
    report_counts: dict[str, int] = {}
    if quiz_q_ids:
        grouped = (
            db.query(QuestionReport.question_id, func.count(QuestionReport.id))
            .filter(QuestionReport.question_id.in_(quiz_q_ids))
            .group_by(QuestionReport.question_id)
            .all()
        )
        report_counts = {str(qid): count for qid, count in grouped}

    questions_out = []
    for q in sorted(quiz.questions, key=lambda x: x.question_order):
        q_dict = _question_out(q, include_answer=True)
        q_dict.update({
            "report_count": report_counts.get(str(q.id), 0),
            "question_type": q.question_type,
            "question_order": q.question_order,
            "explanation": q.explanation,
            "points": q.points,
            "partial_credit_allowed": q.partial_credit_allowed,
            "topic_id": str(q.topic_id) if q.topic_id else None,
            "source_document_id": str(q.source_document_id) if q.source_document_id else None,
            "source_page_number": q.source_page_number,
            "version": q.version,
            "curriculum_mappings": [
                {
                    "id": str(m.id),
                    "topic_id": str(m.topic_id) if m.topic_id else None,
                    "subtopic_id": str(m.subtopic_id) if m.subtopic_id else None,
                    "objective_id": str(m.objective_id) if m.objective_id else None,
                    "bloom_level": m.bloom_level,
                }
                for m in q.curriculum_mappings
            ],
        })
        questions_out.append(q_dict)

    attempt_count = db.query(QuizAttempt).filter(QuizAttempt.quiz_id == quiz.id).count()
    return {
        "id": str(quiz.id),
        "title": quiz.title,
        "description": quiz.description,
        "unit": quiz.unit,
        "chapter": quiz.chapter,
        "generation_type": quiz.generation_type,
        "status": quiz.status.value,
        "version": quiz.version,
        "time_limit_minutes": quiz.time_limit_minutes,
        "passing_percentage": quiz.passing_percentage,
        "class_id": str(quiz.class_id),
        "document_id": str(quiz.document_id) if quiz.document_id else None,
        "question_count": len(quiz.questions),
        "attempt_count": attempt_count,
        "created_at": quiz.created_at.isoformat(),
        "updated_at": quiz.updated_at.isoformat() if quiz.updated_at else None,
        "questions": questions_out,
    }


@router.get("/{quiz_id}/coverage")
def get_quiz_coverage(
    quiz_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    """Faculty retrieves curriculum coverage analysis for a quiz."""
    quiz = access.owned_quiz(db, quiz_id, current_user)
    return coverage_service.analyze_quiz_coverage(db, quiz, persist=True)


@router.post("/{quiz_id}/coverage/recalculate")
def recalculate_quiz_coverage(
    quiz_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    """Faculty triggers on-demand recalculation of curriculum coverage."""
    quiz = access.owned_quiz(db, quiz_id, current_user)
    return coverage_service.analyze_quiz_coverage(db, quiz, persist=True)


@router.post("/{quiz_id}/coverage/acknowledge")
def acknowledge_coverage(
    quiz_id: str,
    payload: schemas.CoverageAcknowledgePayload,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    """Faculty acknowledges advisory coverage warnings prior to publishing."""
    quiz = access.owned_quiz(db, quiz_id, current_user)
    try:
        return coverage_service.acknowledge_coverage_warnings(
            db, quiz.id, faculty_notes=payload.faculty_notes
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/{quiz_id}")
def update_quiz_metadata(
    quiz_id: str,
    payload: schemas.QuizUpdate,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    """Faculty updates quiz metadata."""
    quiz = access.owned_quiz(db, quiz_id, current_user)
    if payload.title is not None:
        quiz.title = payload.title.strip()
    if payload.description is not None:
        quiz.description = payload.description.strip()
    if payload.unit is not None:
        quiz.unit = payload.unit
    if payload.chapter is not None:
        quiz.chapter = payload.chapter
    if payload.document_id is not None:
        doc = access.owned_document(db, str(payload.document_id), current_user)
        quiz.document_id = doc.id
    if payload.time_limit_minutes is not None:
        quiz.time_limit_minutes = payload.time_limit_minutes
    if payload.passing_percentage is not None:
        quiz.passing_percentage = payload.passing_percentage
    if payload.status is not None:
        st = payload.status
        if hasattr(st, "value"):
            st = st.value
        quiz.status = ReviewStatus(st)

    quiz.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(quiz)
    return {
        "id": str(quiz.id),
        "title": quiz.title,
        "description": quiz.description,
        "status": quiz.status.value,
        "version": quiz.version,
    }


@router.delete("/{quiz_id}")
def delete_quiz_endpoint(
    quiz_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    """Faculty deletes unattempted quiz (blocked if student attempts exist)."""
    quiz = access.owned_quiz(db, quiz_id, current_user)
    try:
        quiz_service.delete_quiz(db, quiz)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"message": "Quiz deleted successfully."}


@router.post("/{quiz_id}/publish")
def publish_quiz_endpoint(
    quiz_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    """Faculty publishes quiz, approving questions and making it available to enrolled students."""
    quiz = access.owned_quiz(db, quiz_id, current_user)
    try:
        quiz = quiz_service.publish_quiz(db, quiz)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "id": str(quiz.id),
        "status": quiz.status.value,
        "version": quiz.version,
        "approved_question_count": len([q for q in quiz.questions if q.status == ReviewStatus.approved]),
    }


@router.post("/{quiz_id}/archive")
def archive_quiz_endpoint(
    quiz_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    """Faculty archives quiz, hiding it from new student discovery while preserving attempts."""
    quiz = access.owned_quiz(db, quiz_id, current_user)
    quiz = quiz_service.archive_quiz(db, quiz)
    return {"id": str(quiz.id), "status": quiz.status.value}


@router.post("/{quiz_id}/questions", status_code=201)
def add_question_endpoint(
    quiz_id: str,
    payload: schemas.QuizQuestionCreate,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    """Faculty authors a new question within a quiz."""
    quiz = access.owned_quiz(db, quiz_id, current_user)
    try:
        question = quiz_service.create_question(db, quiz, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _question_out(question, include_answer=True)


@router.post("/{quiz_id}/reorder")
def reorder_questions_endpoint(
    quiz_id: str,
    payload: schemas.QuizReorderPayload,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    """Faculty reorders questions deterministically."""
    quiz = access.owned_quiz(db, quiz_id, current_user)
    try:
        questions = quiz_service.reorder_questions(db, quiz, payload.question_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return [
        {"id": str(q.id), "question_order": q.question_order, "question_text": q.question_text}
        for q in questions
    ]


# --- STUDENT QUIZ DISCOVERY & SUBMISSION ---


@router.get("/{quiz_id}")
def get_quiz_student(
    quiz_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
):
    """Students retrieve approved questions (answer keys and drafts strictly hidden)."""
    quiz = access.enrolled_quiz(db, quiz_id, current_user)
    available_questions = quiz_service.available_questions_for_student(
        db, quiz, str(current_user.id), str(quiz.class_id)
    )
    approved_questions = [q for q in quiz.questions if q.status == ReviewStatus.approved]
    held_question_count = max(0, len(approved_questions) - len(available_questions))
    return {
        "id": str(quiz.id),
        "title": quiz.title,
        "class_id": str(quiz.class_id) if quiz.class_id else None,
        "questions": [_question_out(q, include_answer=False) for q in available_questions],
        "held_question_count": held_question_count,
    }


def _claim_submission(db: Session, quiz: Quiz, student: User, answers_json: str) -> QuizAttempt:
    db.query(User).filter(User.id == student.id).with_for_update().one()
    recent = (
        db.query(QuizAttempt)
        .filter(
            QuizAttempt.student_id == student.id,
            QuizAttempt.quiz_id == quiz.id,
            QuizAttempt.answers == answers_json,
            or_(
                QuizAttempt.completed.is_(True),
                QuizAttempt.started_at >= datetime.utcnow() - DUPLICATE_WINDOW,
            ),
        )
        .first()
    )
    if recent is not None:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This quiz submission was already received. Check your results before submitting again.",
        )
    attempt = QuizAttempt(
        student_id=student.id,
        quiz_id=quiz.id,
        answers=answers_json,
        completed=False,
        quiz_version=quiz.version,
    )
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
    background_tasks: BackgroundTasks,
):
    quiz = access.enrolled_quiz(db, quiz_id, current_user)
    if quiz.status != ReviewStatus.approved:
        raise HTTPException(
            status_code=403,
            detail="This quiz is not currently available for student attempts.",
        )

    def _is_empty_answer(val: Any) -> bool:
        if val is None:
            return True
        if isinstance(val, str) and not val.strip():
            return True
        if isinstance(val, (list, tuple)) and len(val) == 0:
            return True
        return False

    if not payload.answers or all(_is_empty_answer(v) for v in payload.answers.values()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Answer at least one question before submitting.",
        )

    # Validate that question IDs belong to this quiz
    quiz_question_ids = {str(q.id) for q in quiz.questions}
    for q_id_key in payload.answers.keys():
        if str(q_id_key) not in quiz_question_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Question ID '{q_id_key}' does not belong to this quiz.",
            )

    answers = {str(k): v for k, v in payload.answers.items()}
    answers_json = json.dumps(answers, sort_keys=True)
    attempt = _claim_submission(db, quiz, current_user, answers_json)

    try:
        result = await quiz_service.score_attempt(
            db, quiz, str(current_user.id), str(quiz.class_id), answers, source_attempt_id=str(attempt.id)
        )

        ai_candidates = result.get("ai_candidates")
        if ai_candidates:
            background_tasks.add_task(
                quiz_service.run_background_misconception_detection,
                str(current_user.id),
                str(quiz.class_id),
                str(attempt.id),
                ai_candidates,
            )

        attempt = db.get(QuizAttempt, attempt.id)
        attempt.topic_scores = json.dumps(result["topic_scores"])
        attempt.score = result["score"]
        earned = result.get("total_earned_points")
        if earned is None:
            earned = sum(r.get("earned_points", 0.0) for r in result.get("results", []))
        max_p = result.get("total_max_points")
        if max_p is None:
            max_p = sum(r.get("points_possible", 0.0) for r in result.get("results", []))
        attempt.points_earned = float(earned) if earned is not None else None
        attempt.max_points = float(max_p) if max_p is not None else None
        attempt.completed = True
        attempt.completed_at = datetime.utcnow()

        answer_rows = quiz_service.build_answer_rows(
            attempt_id=str(attempt.id),
            student_id=str(current_user.id),
            results=result["results"],
            answered_at=attempt.completed_at,
            class_id=str(quiz.class_id),
        )
        for row in answer_rows:
            db.add(QuizAttemptAnswer(**row))

        db.commit()
    except ValueError as e:
        db.rollback()
        try:
            incomp = db.get(QuizAttempt, attempt.id)
            if incomp and not incomp.completed:
                db.delete(incomp)
                db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        db.rollback()
        try:
            incomp = db.get(QuizAttempt, attempt.id)
            if incomp and not incomp.completed:
                db.delete(incomp)
                db.commit()
        except Exception:
            db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        try:
            incomp = db.get(QuizAttempt, attempt.id)
            if incomp and not incomp.completed:
                db.delete(incomp)
                db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(status_code=500, detail=f"Quiz scoring or saving failed: {exc}")

    updated_mastery = progress_service.update_mastery_after_attempt(
        db, str(current_user.id), str(quiz.class_id), result["topic_scores"],
        topic_passed=result.get("topic_passed"),
    )
    evidence_service.update_engagement(db, current_user.id, count_as_message=False)

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
        "class_id": str(quiz.class_id) if quiz and quiz.class_id else None,
    }
