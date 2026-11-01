import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.orm import Session

from backend.models.db import (
    Category,
    Chunk,
    Class,
    ClassEnrollment,
    Document,
    DocumentStatus,
    LearningObjective,
    Misconception,
    PrerequisiteMap,
    QuestionCurriculumMapping,
    Quiz,
    QuizAttempt,
    QuizAttemptAnswer,
    QuizQuestion,
    Subject,
    SyllabusSubtopic,
    TopicMastery,
    User,
    UserRole,
)
from backend.tests.conftest import auth_headers


@pytest.fixture
def cleanup_phase5_data(db: Session, sample_class: Class, educator_user: User, student_user: User, student_user_2: User):
    def _cleanup():
        db.rollback()
        quizzes = db.query(Quiz).filter(Quiz.class_id == sample_class.id).all()
        quiz_ids = [q.id for q in quizzes]
        if quiz_ids:
            db.query(Misconception).filter(Misconception.class_id == sample_class.id).delete(synchronize_session=False)
            db.query(QuizAttemptAnswer).filter(QuizAttemptAnswer.class_id == sample_class.id).delete(synchronize_session=False)
            db.query(QuizAttempt).filter(QuizAttempt.quiz_id.in_(quiz_ids)).delete(synchronize_session=False)
            q_rows = db.query(QuizQuestion).filter(QuizQuestion.quiz_id.in_(quiz_ids)).all()
            q_ids = [q.id for q in q_rows]
            if q_ids:
                db.query(QuestionCurriculumMapping).filter(QuestionCurriculumMapping.question_id.in_(q_ids)).delete(synchronize_session=False)
                db.query(QuizQuestion).filter(QuizQuestion.quiz_id.in_(quiz_ids)).delete(synchronize_session=False)
            db.query(Quiz).filter(Quiz.id.in_(quiz_ids)).delete(synchronize_session=False)

        docs = db.query(Document).filter(Document.class_id == sample_class.id).all()
        doc_ids = [d.id for d in docs]
        if doc_ids:
            db.query(Chunk).filter(Chunk.document_id.in_(doc_ids)).delete(synchronize_session=False)
            db.query(Document).filter(Document.id.in_(doc_ids)).delete(synchronize_session=False)

        topics = db.query(PrerequisiteMap).filter(PrerequisiteMap.created_by == educator_user.id).all()
        topic_ids = [t.id for t in topics]
        if topic_ids:
            db.query(QuestionCurriculumMapping).filter(QuestionCurriculumMapping.topic_id.in_(topic_ids)).delete(synchronize_session=False)
            db.query(LearningObjective).filter(LearningObjective.topic_id.in_(topic_ids)).delete(synchronize_session=False)
            db.query(SyllabusSubtopic).filter(SyllabusSubtopic.topic_id.in_(topic_ids)).delete(synchronize_session=False)
            db.query(PrerequisiteMap).filter(PrerequisiteMap.id.in_(topic_ids)).delete(synchronize_session=False)

        cls_row = db.get(Class, sample_class.id)
        if cls_row:
            cls_row.subject_id = None
            cls_row.subject = "Physics"
            db.flush()

        db.query(TopicMastery).filter(
            (TopicMastery.class_id == sample_class.id)
            | (TopicMastery.student_id == student_user.id)
            | (TopicMastery.student_id == student_user_2.id)
        ).delete(synchronize_session=False)
        db.query(ClassEnrollment).filter(ClassEnrollment.class_id == sample_class.id).delete(synchronize_session=False)

        subjects = db.query(Subject).filter(Subject.created_by == educator_user.id).all()
        subj_ids = [s.id for s in subjects]
        if subj_ids:
            db.query(Subject).filter(Subject.id.in_(subj_ids)).delete(synchronize_session=False)

        cats = db.query(Category).filter(Category.created_by == educator_user.id).all()
        cat_ids = [c.id for c in cats]
        if cat_ids:
            db.query(Category).filter(Category.id.in_(cat_ids)).delete(synchronize_session=False)

        db.commit()

    _cleanup()
    yield
    _cleanup()


@pytest.fixture
def phase5_env(cleanup_phase5_data, db: Session, sample_class: Class, educator_user: User, student_user: User):
    enrollment = ClassEnrollment(
        class_id=sample_class.id,
        student_id=student_user.id,
    )
    db.add(enrollment)

    cat = Category(name=f"RolloutCat-{uuid.uuid4().hex[:4]}", created_by=educator_user.id)
    db.add(cat)
    db.flush()

    subject = Subject(
        name=f"BioChem Rollout {uuid.uuid4().hex[:6]}",
        category_id=cat.id,
        created_by=educator_user.id,
    )
    db.add(subject)
    db.flush()

    sample_class.subject_id = subject.id
    sample_class.subject = subject.name

    doc = Document(
        title="Biochemistry Pilot Material",
        filename="biochem_pilot.pdf",
        status=DocumentStatus.ready,
        is_indexed=True,
        chunk_count=1,
        class_id=sample_class.id,
        subject_id=subject.id,
        uploaded_by_id=educator_user.id,
    )
    db.add(doc)
    db.flush()

    topic = PrerequisiteMap(
        subject_id=subject.id,
        topic="Krebs Cycle",
        description="Citric acid cycle enzymatic breakdown and energy generation",
        order_index=1,
        unit=2,
        is_canonical=True,
        created_by=educator_user.id,
        source_document_id=doc.id,
    )
    db.add(topic)
    db.flush()

    chunk = Chunk(
        document_id=doc.id,
        class_id=sample_class.id,
        subject_id=subject.id,
        subject=subject.name,
        topic="Krebs Cycle",
        page_number=12,
        chunk_index=1,
        token_count=120,
        section_heading="Citric Acid Cycle",
        text="The Krebs cycle oxidizes acetyl-CoA into CO2, producing ATP, NADH, and FADH2.",
        contextual_prefix="Chapter 3: Krebs Cycle",
        full_text="The Krebs cycle oxidizes acetyl-CoA into CO2, producing ATP, NADH, and FADH2.",
        embedding=[0.05] * 384,
    )
    db.add(chunk)
    db.commit()

    return {
        "subject": subject,
        "doc": doc,
        "topic": topic,
        "chunk": chunk,
    }


def test_question_feedback_reporting_lifecycle(client, db: Session, sample_class: Class, educator_user: User, student_user: User, student_user_2: User, phase5_env):
    """Verifies that students and faculty can report question issues,
    preserving context and provenance without leaking secrets."""
    topic = phase5_env["topic"]

    # 1. Generate topic practice quiz for student 1
    mock_candidates = [
        {
            "question": "Which molecule enters the Krebs cycle to produce NADH and FADH2?",
            "question_type": "single_choice",
            "options": ["Acetyl-CoA", "Lactate", "Pyruvate", "Glucose"],
            "correct_answer": "Acetyl-CoA",
            "difficulty": "medium",
            "bloom_level": "remember",
            "explanation": "Acetyl-CoA is the initial substrate entering the citric acid cycle.",
            "chunk_index": 1,
        }
    ]

    with patch("backend.services.rag_service.get_llm_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.generate.return_value = json.dumps(mock_candidates)
        mock_get_provider.return_value = (mock_provider, 0)

        gen_resp = client.post(
            "/api/v1/quizzes/topic-quiz",
            headers=auth_headers(student_user),
            json={
                "class_id": str(sample_class.id),
                "topic": topic.topic,
                "topic_id": str(topic.id),
                "num_questions": 1,
            },
        )
    assert gen_resp.status_code == 201
    quiz_id = gen_resp.json()["quiz_id"]

    # Retrieve question id
    runner_resp = client.get(f"/api/v1/quizzes/{quiz_id}", headers=auth_headers(student_user))
    assert runner_resp.status_code == 200
    q_item = runner_resp.json()["questions"][0]
    question_id = q_item["id"]

    # 2. Student submits issue report on ambiguous explanation
    report_payload = {
        "category": "ambiguous_wording",
        "comment": "The options could be more specific regarding cellular location.",
    }
    rep_resp = client.post(
        f"/api/v1/quizzes/questions/{question_id}/report",
        headers=auth_headers(student_user),
        json=report_payload,
    )
    assert rep_resp.status_code == 201, rep_resp.text
    rep_data = rep_resp.json()
    assert rep_data["question_id"] == question_id
    assert rep_data["quiz_id"] == quiz_id
    assert rep_data["category"] == "ambiguous_wording"
    assert rep_data["status"] == "received"
    assert "report_id" in rep_data

    # 3. Non-enrolled student 2 cannot report question -> 404
    non_enrolled_rep = client.post(
        f"/api/v1/quizzes/questions/{question_id}/report",
        headers=auth_headers(student_user_2),
        json=report_payload,
    )
    assert non_enrolled_rep.status_code == 404

    # 4. Educator can also report or review question
    ed_rep = client.post(
        f"/api/v1/quizzes/questions/{question_id}/report",
        headers=auth_headers(educator_user),
        json={
            "category": "incorrect_difficulty",
            "comment": "Educator audit: Bloom level should be classified as understand instead of remember.",
        },
    )
    assert ed_rep.status_code == 201
    assert ed_rep.json()["category"] == "incorrect_difficulty"

    # 5. Non-existent question ID -> 404
    fake_rep = client.post(
        f"/api/v1/quizzes/questions/{uuid.uuid4()}/report",
        headers=auth_headers(student_user),
        json=report_payload,
    )
    assert fake_rep.status_code == 404


def test_faculty_governance_and_practice_distinction(client, db: Session, sample_class: Class, educator_user: User, student_user: User, phase5_env):
    """Verifies that faculty listing distinguishes topic-practice quizzes from standard assessments,
    and supports reviewing and rejecting flawed questions."""
    topic = phase5_env["topic"]

    # 1. Student generates a topic practice quiz
    mock_candidates = [
        {
            "question": "What is the primary role of FADH2 in the Krebs cycle?",
            "question_type": "single_choice",
            "options": ["Electron carrier", "Structural protein", "Enzyme activator", "Buffer"],
            "correct_answer": "Electron carrier",
            "difficulty": "medium",
            "bloom_level": "understand",
            "explanation": "FADH2 acts as an electron carrier donating to complex II.",
            "chunk_index": 1,
        }
    ]

    with patch("backend.services.rag_service.get_llm_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.generate.return_value = json.dumps(mock_candidates)
        mock_get_provider.return_value = (mock_provider, 0)

        gen_resp = client.post(
            "/api/v1/quizzes/topic-quiz",
            headers=auth_headers(student_user),
            json={
                "class_id": str(sample_class.id),
                "topic": topic.topic,
                "topic_id": str(topic.id),
                "num_questions": 1,
            },
        )
    assert gen_resp.status_code == 201
    quiz_id = gen_resp.json()["quiz_id"]

    # 2. Educator lists class quizzes: verifies generation_type is clearly distinguished
    list_resp = client.get(
        f"/api/v1/quizzes?class_id={sample_class.id}",
        headers=auth_headers(educator_user),
    )
    assert list_resp.status_code == 200
    quizzes = list_resp.json()
    practice_quiz = next((q for q in quizzes if q["id"] == quiz_id), None)
    assert practice_quiz is not None
    assert practice_quiz["generation_type"] == "topic_practice"

    # 3. Educator inspects full faculty view
    fac_resp = client.get(
        f"/api/v1/quizzes/{quiz_id}/faculty",
        headers=auth_headers(educator_user),
    )
    assert fac_resp.status_code == 200
    fac_data = fac_resp.json()
    assert fac_data["generation_type"] == "topic_practice"
    assert len(fac_data["questions"]) == 1
    q_data = fac_data["questions"][0]
    question_id = q_data["id"]
    assert q_data["correct_answer"] == "Electron carrier"
    assert q_data["explanation"] is not None

    # 4. Educator rejects question for academic revision
    patch_resp = client.patch(
        f"/api/v1/quizzes/questions/{question_id}",
        headers=auth_headers(educator_user),
        json={"status": "rejected"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "rejected"

    # Verify status in database
    q_row = db.get(QuizQuestion, uuid.UUID(question_id))
    assert q_row.status.value == "rejected"
