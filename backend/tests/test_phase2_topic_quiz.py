import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from backend.models.db import (
    Category,
    Chunk,
    Class,
    ClassEnrollment,
    Document,
    DocumentStatus,
    LearningObjective,
    PrerequisiteMap,
    QuestionCurriculumMapping,
    QuestionDifficulty,
    QuestionType,
    Quiz,
    QuizAttempt,
    QuizAttemptAnswer,
    QuizQuestion,
    ReviewStatus,
    Subject,
    SyllabusSubtopic,
    TopicMastery,
    User,
    UserRole,
)
from backend.tests.conftest import auth_headers


@pytest.fixture(autouse=True)
def cleanup_topic_quiz_data(db, sample_class, educator_user, student_user, student_user_2):
    """Ensure database state is clean before and after each topic quiz test."""
    def _cleanup():
        quizzes = db.query(Quiz).filter(Quiz.class_id == sample_class.id).all()
        quiz_ids = [q.id for q in quizzes]
        if quiz_ids:
            db.query(QuizAttemptAnswer).filter(QuizAttemptAnswer.class_id == sample_class.id).delete(synchronize_session=False)
            db.query(QuizAttempt).filter(QuizAttempt.quiz_id.in_(quiz_ids)).delete(synchronize_session=False)
            q_rows = db.query(QuizQuestion).filter(QuizQuestion.quiz_id.in_(quiz_ids)).all()
            q_ids = [q.id for q in q_rows]
            if q_ids:
                db.query(QuestionCurriculumMapping).filter(QuestionCurriculumMapping.question_id.in_(q_ids)).delete(synchronize_session=False)
                db.query(QuizQuestion).filter(QuizQuestion.quiz_id.in_(quiz_ids)).delete(synchronize_session=False)
            db.query(Quiz).filter(Quiz.id.in_(quiz_ids)).delete(synchronize_session=False)

        # Remove chunks and documents for this class
        docs = db.query(Document).filter(Document.class_id == sample_class.id).all()
        doc_ids = [d.id for d in docs]
        if doc_ids:
            db.query(Chunk).filter(Chunk.document_id.in_(doc_ids)).delete(synchronize_session=False)
            db.query(Document).filter(Document.id.in_(doc_ids)).delete(synchronize_session=False)

        # Clean topics created by educator
        topics = db.query(PrerequisiteMap).filter(PrerequisiteMap.created_by == educator_user.id).all()
        topic_ids = [t.id for t in topics]
        if topic_ids:
            db.query(QuestionCurriculumMapping).filter(QuestionCurriculumMapping.topic_id.in_(topic_ids)).delete(synchronize_session=False)
            db.query(LearningObjective).filter(LearningObjective.topic_id.in_(topic_ids)).delete(synchronize_session=False)
            db.query(SyllabusSubtopic).filter(SyllabusSubtopic.topic_id.in_(topic_ids)).delete(synchronize_session=False)
            db.query(PrerequisiteMap).filter(PrerequisiteMap.id.in_(topic_ids)).delete(synchronize_session=False)

        # Reset class subject link
        cls_row = db.get(Class, sample_class.id)
        if cls_row:
            cls_row.subject_id = None
            cls_row.subject = "Physics"
            db.flush()

        # Cleanup student masteries and enrollments before subjects
        db.query(TopicMastery).filter(
            (TopicMastery.class_id == sample_class.id)
            | (TopicMastery.student_id == student_user.id)
            | (TopicMastery.student_id == student_user_2.id)
        ).delete(synchronize_session=False)
        db.query(ClassEnrollment).filter(ClassEnrollment.class_id == sample_class.id).delete(synchronize_session=False)

        # Clean subjects and categories created by educator
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
def curriculum_fixture(db, sample_class, educator_user, student_user):
    """Sets up a subject, enrolled student, canonical topic, and grounded document with chunks."""
    # Enroll student in class
    enrollment = ClassEnrollment(
        class_id=sample_class.id,
        student_id=student_user.id,
    )
    db.add(enrollment)

    # Category setup
    cat = db.query(Category).first()
    if not cat:
        cat = Category(name=f"Science-{uuid.uuid4().hex[:4]}", created_by=educator_user.id)
        db.add(cat)
        db.flush()

    # Subject setup
    subject = Subject(
        name=f"Cell Biology {uuid.uuid4().hex[:6]}",
        category_id=cat.id,
        created_by=educator_user.id,
    )
    db.add(subject)
    db.flush()

    sample_class.subject_id = subject.id
    sample_class.subject = subject.name

    # Document
    doc = Document(
        title="Cellular Processes Textbook",
        filename="bio_processes.pdf",
        status=DocumentStatus.ready,
        is_indexed=True,
        chunk_count=2,
        class_id=sample_class.id,
        subject_id=subject.id,
        uploaded_by_id=educator_user.id,
    )
    db.add(doc)
    db.flush()

    # Topic in PrerequisiteMap
    topic = PrerequisiteMap(
        subject_id=subject.id,
        subject=subject.name,
        topic="Cellular Respiration",
        unit=2,
        order_index=1,
        is_canonical=True,
        source_document_id=doc.id,
        source_page_number=45,
        created_by=educator_user.id,
    )
    db.add(topic)
    db.flush()

    # Two distinct chunks with different content and page numbers
    chunk1 = Chunk(
        document_id=doc.id,
        class_id=sample_class.id,
        subject_id=subject.id,
        subject=subject.name,
        topic="Cellular Respiration",
        page_number=45,
        chunk_index=0,
        token_count=120,
        section_heading="Glycolysis and ATP Production",
        text="Glycolysis occurs in the cytoplasm and breaks down glucose into pyruvate, yielding a net gain of 2 ATP molecules.",
        contextual_prefix="Chapter 2: Energy",
        full_text="Chapter 2: Energy. Glycolysis occurs in the cytoplasm and breaks down glucose into pyruvate, yielding a net gain of 2 ATP molecules.",
        embedding=[0.05] * 384,
    )
    chunk2 = Chunk(
        document_id=doc.id,
        class_id=sample_class.id,
        subject_id=subject.id,
        subject=subject.name,
        topic="Cellular Respiration",
        page_number=47,
        chunk_index=1,
        token_count=130,
        section_heading="Krebs Cycle and Mitochondria",
        text="The Krebs cycle takes place in the mitochondrial matrix, producing NADH and FADH2 for the electron transport chain.",
        contextual_prefix="Chapter 2: Energy",
        full_text="Chapter 2: Energy. The Krebs cycle takes place in the mitochondrial matrix, producing NADH and FADH2 for the electron transport chain.",
        embedding=[0.06] * 384,
    )
    db.add_all([chunk1, chunk2])
    db.commit()

    return {
        "subject": subject,
        "document": doc,
        "topic": topic,
        "chunk1": chunk1,
        "chunk2": chunk2,
    }


def test_topic_quiz_generation_success(client, db, sample_class, student_user, curriculum_fixture):
    """Tests successful topic quiz generation with grounding, schema validation, and provenance."""
    topic = curriculum_fixture["topic"]
    chunk1 = curriculum_fixture["chunk1"]
    chunk2 = curriculum_fixture["chunk2"]

    mock_llm_output = json.dumps([
        {
            "question": "Where does glycolysis occur within the cell?",
            "question_type": "single_choice",
            "options": ["Cytoplasm", "Mitochondrial matrix", "Nucleus", "Ribosome"],
            "correct_answer": "Cytoplasm",
            "difficulty": "easy",
            "explanation": "Glycolysis takes place in the cytoplasm as stated in the textbook.",
            "chunk_index": 1,
        },
        {
            "question": "Which of the following are electron carriers produced during the Krebs cycle?",
            "question_type": "multiple_choice",
            "options": ["NADH", "FADH2", "Pyruvate", "Glucose"],
            "correct_answer": ["NADH", "FADH2"],
            "difficulty": "medium",
            "explanation": "The Krebs cycle produces NADH and FADH2.",
            "chunk_index": 2,
        },
        {
            "question": "Glycolysis requires oxygen to produce ATP.",
            "question_type": "true_false",
            "options": ["True", "False"],
            "correct_answer": "False",
            "difficulty": "medium",
            "explanation": "Glycolysis occurs anaerobically.",
            "chunk_index": 1,
        },
    ])

    with patch("backend.services.rag_service.get_llm_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.generate.return_value = mock_llm_output
        mock_get_provider.return_value = (mock_provider, 0)

        response = client.post(
            "/api/v1/quizzes/topic-quiz",
            headers=auth_headers(student_user),
            json={
                "class_id": str(sample_class.id),
                "topic": topic.topic,
                "topic_id": str(topic.id),
                "num_questions": 3,
            },
        )

    assert response.status_code == 201, response.text
    data = response.json()
    assert "quiz_id" in data
    assert data["topic"] == "Cellular Respiration"
    assert data["question_count"] == 3
    assert data["status"] == "approved"

    # Verify quiz in database
    quiz_row = db.get(Quiz, uuid.UUID(data["quiz_id"]))
    assert quiz_row is not None
    assert quiz_row.generation_type == "topic_practice"
    assert quiz_row.status == ReviewStatus.approved
    assert quiz_row.created_by_id == student_user.id
    assert len(quiz_row.questions) == 3

    # Verify question provenance attribution
    q1 = next(q for q in quiz_row.questions if q.question_type == "single_choice")
    assert q1.source_chunk_id in {chunk1.id, chunk2.id}
    assert q1.source_page_number in {45, 47}
    assert q1.topic == "Cellular Respiration"
    assert q1.topic_id == topic.id

    q2 = next(q for q in quiz_row.questions if q.question_type == "multiple_choice")
    assert q2.source_chunk_id in {chunk1.id, chunk2.id}
    assert q2.source_page_number in {45, 47}
    assert q2.partial_credit_allowed is True

    # Ensure questions are attributed across distinct supporting chunks (not all to chunk 0)
    all_assigned_chunks = {q.source_chunk_id for q in quiz_row.questions if q.source_chunk_id}
    assert len(all_assigned_chunks) >= 2

    # Verify curriculum mapping created
    mappings = db.query(QuestionCurriculumMapping).filter(
        QuestionCurriculumMapping.topic_id == topic.id
    ).all()
    assert len(mappings) == 3


def test_topic_quiz_runner_and_submission(client, db, sample_class, student_user, curriculum_fixture):
    """Verifies that the generated topic quiz can be retrieved by student runner and submitted for scoring."""
    topic = curriculum_fixture["topic"]

    mock_llm_output = json.dumps([
        {
            "question": "What is the net gain of ATP molecules from glycolysis?",
            "question_type": "single_choice",
            "options": ["2 ATP", "4 ATP", "36 ATP", "0 ATP"],
            "correct_answer": "2 ATP",
            "difficulty": "easy",
            "explanation": "Glycolysis yields a net gain of 2 ATP.",
            "chunk_index": 1,
        }
    ])

    with patch("backend.services.rag_service.get_llm_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.generate.return_value = mock_llm_output
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

    # 1. Student fetches quiz from runner: GET /quizzes/{quiz_id}
    runner_resp = client.get(
        f"/api/v1/quizzes/{quiz_id}",
        headers=auth_headers(student_user),
    )
    assert runner_resp.status_code == 200
    runner_data = runner_resp.json()
    assert runner_data["id"] == quiz_id
    assert len(runner_data["questions"]) == 1
    # Ensure answer keys are sanitized for student
    q_item = runner_data["questions"][0]
    assert "correct_answer" not in q_item
    assert "explanation" not in q_item
    q_id = q_item["id"]

    # 2. Student submits attempt: POST /quizzes/{quiz_id}/attempt
    attempt_resp = client.post(
        f"/api/v1/quizzes/{quiz_id}/attempt",
        headers=auth_headers(student_user),
        json={"answers": {q_id: "2 ATP"}},
    )
    assert attempt_resp.status_code == 201, attempt_resp.text
    attempt_data = attempt_resp.json()
    assert attempt_data["score"] == 100.0
    assert "Cellular Respiration" in attempt_data["topic_scores"]

    # Verify TopicMastery was updated
    mastery = db.query(TopicMastery).filter(
        TopicMastery.student_id == student_user.id,
        TopicMastery.topic == "Cellular Respiration",
    ).first()
    assert mastery is not None
    assert mastery.attempt_count >= 1
    assert mastery.mastery_score >= 0.5


def test_topic_quiz_isolation_between_students(client, db, sample_class, student_user, student_user_2, curriculum_fixture):
    """Ensures practice quizzes created by student A cannot be accessed or attempted by student B."""
    topic = curriculum_fixture["topic"]

    # Enroll student 2 in the same class
    db.add(ClassEnrollment(class_id=sample_class.id, student_id=student_user_2.id))
    db.commit()

    mock_llm_output = json.dumps([
        {
            "question": "Sample Question",
            "question_type": "single_choice",
            "options": ["A", "B", "C", "D"],
            "correct_answer": "A",
            "difficulty": "easy",
            "chunk_index": 1,
        }
    ])

    with patch("backend.services.rag_service.get_llm_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.generate.return_value = mock_llm_output
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

    # Student 2 tries to access student 1's practice quiz -> 404
    resp_s2 = client.get(
        f"/api/v1/quizzes/{quiz_id}",
        headers=auth_headers(student_user_2),
    )
    assert resp_s2.status_code == 404

    # Student 2 tries to submit attempt -> 404
    attempt_s2 = client.post(
        f"/api/v1/quizzes/{quiz_id}/attempt",
        headers=auth_headers(student_user_2),
        json={"answers": {}},
    )
    assert attempt_s2.status_code == 404

    # Ensure practice quizzes do not appear in class /available catalog
    avail_resp = client.get(
        f"/api/v1/quizzes/available?class_id={sample_class.id}",
        headers=auth_headers(student_user),
    )
    assert avail_resp.status_code == 200
    available_quizzes = avail_resp.json()
    quiz_ids = [q["id"] for q in available_quizzes]
    assert quiz_id not in quiz_ids


def test_topic_quiz_unauthorized_student(client, db, sample_class, student_user_2, curriculum_fixture):
    """Tests that unenrolled student is rejected with 404."""
    topic = curriculum_fixture["topic"]
    # student_user_2 is NOT enrolled in sample_class
    response = client.post(
        "/api/v1/quizzes/topic-quiz",
        headers=auth_headers(student_user_2),
        json={
            "class_id": str(sample_class.id),
            "topic": topic.topic,
            "topic_id": str(topic.id),
            "num_questions": 3,
        },
    )
    assert response.status_code == 404


def test_topic_quiz_invalid_topic_id(client, sample_class, student_user, curriculum_fixture):
    """Tests rejection when non-existent topic ID is provided."""
    fake_topic_id = str(uuid.uuid4())
    response = client.post(
        "/api/v1/quizzes/topic-quiz",
        headers=auth_headers(student_user),
        json={
            "class_id": str(sample_class.id),
            "topic": "Non Existent Topic",
            "topic_id": fake_topic_id,
            "num_questions": 3,
        },
    )
    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()


def test_topic_quiz_insufficient_materials(client, db, sample_class, student_user, educator_user):
    """Tests rejection when class has no curriculum chunks for the topic."""
    # Class with enrolled student and topic, but 0 documents or chunks
    enrollment = ClassEnrollment(class_id=sample_class.id, student_id=student_user.id)
    db.add(enrollment)
    cat = db.query(Category).first()
    if not cat:
        cat = Category(name=f"Science-{uuid.uuid4().hex[:4]}", created_by=educator_user.id)
        db.add(cat)
        db.flush()
    subject = Subject(name=f"Empty Subj {uuid.uuid4().hex[:4]}", category_id=cat.id, created_by=educator_user.id)
    db.add(subject)
    db.flush()
    sample_class.subject_id = subject.id
    sample_class.subject = subject.name

    topic = PrerequisiteMap(
        subject_id=subject.id,
        subject=subject.name,
        topic="Dark Matter",
        created_by=educator_user.id,
    )
    db.add(topic)
    db.commit()

    response = client.post(
        "/api/v1/quizzes/topic-quiz",
        headers=auth_headers(student_user),
        json={
            "class_id": str(sample_class.id),
            "topic": topic.topic,
            "topic_id": str(topic.id),
            "num_questions": 3,
        },
    )
    assert response.status_code == 400
    assert "no curriculum materials found" in response.json()["detail"].lower()


def test_topic_quiz_llm_failure(client, sample_class, student_user, curriculum_fixture):
    """Tests handling when LLM returns invalid/unparseable JSON."""
    topic = curriculum_fixture["topic"]

    with patch("backend.services.rag_service.get_llm_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.generate.return_value = "Sorry, I cannot generate questions right now."
        mock_get_provider.return_value = (mock_provider, 0)

        response = client.post(
            "/api/v1/quizzes/topic-quiz",
            headers=auth_headers(student_user),
            json={
                "class_id": str(sample_class.id),
                "topic": topic.topic,
                "topic_id": str(topic.id),
                "num_questions": 3,
            },
        )
    assert response.status_code == 400
    assert "failed to produce valid question json" in response.json()["detail"].lower()
