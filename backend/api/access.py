import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.models.db import (
    Chunk,
    Class,
    ClassEnrollment,
    Document,
    IngestionJob,
    Quiz,
    QuizQuestion,
    ReviewStatus,
    Subject,
    User,
)


def _not_found(label: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found.")


def parse_uuid(value, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise _not_found(label)


def is_enrolled(db: Session, class_id, student_id) -> bool:
    return (
        db.query(ClassEnrollment.id)
        .filter(ClassEnrollment.class_id == class_id, ClassEnrollment.student_id == student_id)
        .first()
        is not None
    )


def owned_class(db: Session, class_id, user: User) -> Class:
    row = db.get(Class, parse_uuid(class_id, "Class"))
    if row is None or row.educator_id != user.id:
        raise _not_found("Class")
    return row


def enrolled_class(db: Session, class_id, user: User) -> Class:
    row = db.get(Class, parse_uuid(class_id, "Class"))
    if row is None or not is_enrolled(db, row.id, user.id):
        raise _not_found("Class")
    return row


def student_class_id(db: Session, user: User, requested_class_id) -> str:
    if requested_class_id:
        return str(enrolled_class(db, requested_class_id, user).id)
    enrollment = (
        db.query(ClassEnrollment)
        .filter(ClassEnrollment.student_id == user.id)
        .order_by(ClassEnrollment.enrolled_at)
        .first()
    )
    if enrollment is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not enrolled in any class. Join one from the classes page first.",
        )
    return str(enrollment.class_id)


def owned_student_in_class(db: Session, student_id, class_id, user: User) -> Class:
    class_row = owned_class(db, class_id, user)
    if not is_enrolled(db, class_row.id, parse_uuid(student_id, "Student")):
        raise _not_found("Student")
    return class_row


def owned_document(db: Session, document_id, user: User) -> Document:
    doc = db.get(Document, parse_uuid(document_id, "Document"))
    if doc is None or doc.deleted or doc.class_ is None or doc.class_.educator_id != user.id:
        raise _not_found("Document")
    return doc


def owned_job(db: Session, job_id, user: User) -> IngestionJob:
    job = db.get(IngestionJob, parse_uuid(job_id, "Job"))
    if job is None:
        raise _not_found("Job")
    doc = db.get(Document, job.document_id)
    if doc is None or doc.class_ is None or doc.class_.educator_id != user.id:
        raise _not_found("Job")
    return job


def owned_quiz(db: Session, quiz_id, user: User) -> Quiz:
    quiz = db.get(Quiz, parse_uuid(quiz_id, "Quiz"))
    if quiz is None:
        raise _not_found("Quiz")
    class_row = db.get(Class, quiz.class_id)
    if class_row is None or class_row.educator_id != user.id:
        raise _not_found("Quiz")
    return quiz


def owned_question(db: Session, question_id, user: User) -> QuizQuestion:
    question = db.get(QuizQuestion, parse_uuid(question_id, "Question"))
    if question is None:
        raise _not_found("Question")
    owned_quiz(db, question.quiz_id, user)
    return question


def enrolled_quiz(db: Session, quiz_id, user: User) -> Quiz:
    quiz = db.get(Quiz, parse_uuid(quiz_id, "Quiz"))
    if quiz is None or quiz.status != ReviewStatus.approved or not is_enrolled(db, quiz.class_id, user.id):
        raise _not_found("Quiz")
    return quiz


def existing_subject(db: Session, subject_id) -> Subject:
    subject = db.get(Subject, parse_uuid(subject_id, "Subject"))
    if subject is None:
        raise _not_found("Subject")
    return subject


def owned_subject(db: Session, subject_id, user: User) -> Subject:
    subject = existing_subject(db, subject_id)
    if subject.created_by != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the educator who created this subject can change it.",
        )
    return subject


def owned_chunk(db: Session, chunk_id, user: User) -> Chunk:
    chunk = db.get(Chunk, parse_uuid(chunk_id, "Chunk"))
    if chunk is None:
        raise _not_found("Chunk")
    class_id = chunk.class_id
    if class_id is None:
        doc = db.get(Document, chunk.document_id)
        class_id = doc.class_id if doc else None
    class_row = db.get(Class, class_id) if class_id else None
    if class_row is None or class_row.educator_id != user.id:
        raise _not_found("Chunk")
    return chunk
