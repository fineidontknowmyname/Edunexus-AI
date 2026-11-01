import json
import uuid
import pytest
from backend.core.database import SessionLocal
from backend.models.db import (
    Class,
    ClassEnrollment,
    CoverageStatus,
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
    QuizCoverageReport,
    QuizQuestion,
    ReviewStatus,
    Subject,
    SyllabusSubtopic,
    User,
    UserRole,
)
from backend.services.quiz_service import evaluate_question_answer
from backend.tests.conftest import auth_headers


@pytest.fixture(autouse=True)
def cleanup_quiz_database(db, sample_class, educator_user):
    """Ensure all test quizzes, attempts, questions, and curriculum records are wiped
    before and after each test to prevent foreign key errors during user/class teardown.
    """
    def _cleanup():
        # 1. Clean quiz attempt answers
        db.query(QuizAttemptAnswer).filter(QuizAttemptAnswer.class_id == sample_class.id).delete()
        
        # 2. Find quizzes for this class
        quizzes = db.query(Quiz).filter(Quiz.class_id == sample_class.id).all()
        quiz_ids = [q.id for q in quizzes]
        if quiz_ids:
            db.query(QuizAttempt).filter(QuizAttempt.quiz_id.in_(quiz_ids)).delete(synchronize_session=False)
            db.query(QuizCoverageReport).filter(QuizCoverageReport.quiz_id.in_(quiz_ids)).delete(synchronize_session=False)
            
            q_rows = db.query(QuizQuestion).filter(QuizQuestion.quiz_id.in_(quiz_ids)).all()
            q_ids = [q.id for q in q_rows]
            if q_ids:
                db.query(QuestionCurriculumMapping).filter(QuestionCurriculumMapping.question_id.in_(q_ids)).delete(synchronize_session=False)
                db.query(QuizQuestion).filter(QuizQuestion.quiz_id.in_(quiz_ids)).delete(synchronize_session=False)
            
            db.query(Quiz).filter(Quiz.id.in_(quiz_ids)).delete(synchronize_session=False)

        # 3. Clean any topics created by educator
        topics = db.query(PrerequisiteMap).filter(PrerequisiteMap.created_by == educator_user.id).all()
        topic_ids = [t.id for t in topics]
        if topic_ids:
            db.query(QuestionCurriculumMapping).filter(QuestionCurriculumMapping.topic_id.in_(topic_ids)).delete(synchronize_session=False)
            db.query(LearningObjective).filter(LearningObjective.topic_id.in_(topic_ids)).delete(synchronize_session=False)
            db.query(SyllabusSubtopic).filter(SyllabusSubtopic.topic_id.in_(topic_ids)).delete(synchronize_session=False)
            db.query(PrerequisiteMap).filter(PrerequisiteMap.id.in_(topic_ids)).delete(synchronize_session=False)
        
        db.commit()

    _cleanup()
    yield
    _cleanup()


@pytest.fixture
def test_hierarchy(db, educator_user, sample_class):
    """Creates Subject, Topic, Subtopic, Objective, and Document for mapping tests."""
    subject = db.query(Subject).first()
    if not subject:
        subject = Subject(name=f"Subj-{uuid.uuid4().hex[:6]}", code=f"S-{uuid.uuid4().hex[:4]}")
        db.add(subject)
        db.flush()

    topic = PrerequisiteMap(
        subject_id=subject.id,
        subject=subject.name,
        topic=f"Topic-{uuid.uuid4().hex[:6]}",
        unit=1,
        order_index=1,
        is_canonical=True,
        created_by=educator_user.id,
    )
    db.add(topic)
    db.flush()

    subtopic = SyllabusSubtopic(
        topic_id=topic.id,
        name=f"Subtopic-{uuid.uuid4().hex[:6]}",
        order_index=1,
    )
    db.add(subtopic)
    db.flush()

    objective = LearningObjective(
        topic_id=topic.id,
        subtopic_id=subtopic.id,
        statement=f"Objective-{uuid.uuid4().hex[:6]}",
    )
    db.add(objective)
    db.flush()

    doc = Document(
        title="Test Syllabus Ingested Doc",
        filename="test_doc.pdf",
        file_path="uploads/test_doc.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        file_hash_sha256="dummychecksum",
        uploaded_by_id=educator_user.id,
        class_id=sample_class.id,
        status=DocumentStatus.ready,
    )
    db.add(doc)
    db.commit()

    yield {
        "subject": subject,
        "topic": topic,
        "subtopic": subtopic,
        "objective": objective,
        "document": doc,
    }

    # Teardown hierarchy
    db.query(QuestionCurriculumMapping).filter(QuestionCurriculumMapping.topic_id == topic.id).delete()
    db.query(LearningObjective).filter(LearningObjective.id == objective.id).delete()
    db.query(SyllabusSubtopic).filter(SyllabusSubtopic.id == subtopic.id).delete()
    db.query(PrerequisiteMap).filter(PrerequisiteMap.id == topic.id).delete()
    db.query(Document).filter(Document.id == doc.id).delete()
    db.commit()


def test_create_draft_quiz_and_listing(client, educator_user, sample_class):
    """Faculty creates a draft quiz and lists it."""
    payload = {
        "class_id": str(sample_class.id),
        "title": "Operating Systems Quiz 1",
        "description": "Process Management and Scheduling",
        "unit": 1,
        "chapter": 1,
        "time_limit_minutes": 30,
        "passing_percentage": 70.0,
    }
    resp = client.post("/api/v1/quizzes", json=payload, headers=auth_headers(educator_user))
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == payload["title"]
    assert data["status"] == "draft"
    assert data["generation_type"] == "manual"
    quiz_id = data["id"]

    # List quizzes for class
    list_resp = client.get(
        f"/api/v1/quizzes?class_id={sample_class.id}&status_filter=draft",
        headers=auth_headers(educator_user),
    )
    assert list_resp.status_code == 200
    quizzes = list_resp.json()
    assert any(q["id"] == quiz_id for q in quizzes)


def test_create_single_choice_question(client, educator_user, sample_class, test_hierarchy):
    """Create single-choice question with source doc and curriculum mapping."""
    q_resp = client.post(
        "/api/v1/quizzes",
        json={"class_id": str(sample_class.id), "title": "SC Test Quiz"},
        headers=auth_headers(educator_user),
    )
    quiz_id = q_resp.json()["id"]

    q_payload = {
        "question_text": "What is the primary role of an OS kernel?",
        "question_type": "single_choice",
        "options": ["Resource management", "Word processing", "Web browsing", "Video rendering"],
        "correct_answer": "Resource management",
        "explanation": "The kernel manages CPU, memory, and devices.",
        "difficulty": "medium",
        "points": 2.0,
        "topic_id": str(test_hierarchy["topic"].id),
        "subtopic_id": str(test_hierarchy["subtopic"].id),
        "objective_id": str(test_hierarchy["objective"].id),
        "source_document_id": str(test_hierarchy["document"].id),
        "source_page_number": 4,
    }
    add_resp = client.post(
        f"/api/v1/quizzes/{quiz_id}/questions",
        json=q_payload,
        headers=auth_headers(educator_user),
    )
    assert add_resp.status_code == 201
    q_data = add_resp.json()
    assert q_data["question_text"] == q_payload["question_text"]
    assert q_data["question_order"] == 1
    assert q_data["source_document_id"] == str(test_hierarchy["document"].id)
    assert q_data["source_page_number"] == 4
    assert q_data["correct_answer"] == "Resource management"

    # Verify Faculty View includes answer key and mappings
    fac_resp = client.get(
        f"/api/v1/quizzes/{quiz_id}/faculty",
        headers=auth_headers(educator_user),
    )
    assert fac_resp.status_code == 200
    fac_data = fac_resp.json()
    assert len(fac_data["questions"]) == 1
    q_detail = fac_data["questions"][0]
    assert q_detail["correct_answer"] == "Resource management"
    assert q_detail["explanation"] == "The kernel manages CPU, memory, and devices."
    assert len(q_detail["curriculum_mappings"]) == 1
    assert q_detail["curriculum_mappings"][0]["topic_id"] == str(test_hierarchy["topic"].id)


def test_create_multiple_choice_question(client, educator_user, sample_class):
    """Create multiple-choice question with multiple correct answers and partial credit."""
    q_resp = client.post(
        "/api/v1/quizzes",
        json={"class_id": str(sample_class.id), "title": "MC Test Quiz"},
        headers=auth_headers(educator_user),
    )
    quiz_id = q_resp.json()["id"]

    mc_payload = {
        "question_text": "Which of the following are page replacement algorithms? (Choose two)",
        "question_type": "multiple_choice",
        "options": ["LRU", "FIFO", "Round Robin", "Dijkstra"],
        "correct_answer": ["LRU", "FIFO"],
        "explanation": "LRU and FIFO are page replacement algorithms.",
        "difficulty": "hard",
        "points": 4.0,
        "partial_credit_allowed": True,
    }
    add_resp = client.post(
        f"/api/v1/quizzes/{quiz_id}/questions",
        json=mc_payload,
        headers=auth_headers(educator_user),
    )
    assert add_resp.status_code == 201
    q_data = add_resp.json()
    assert q_data["question_type"] == "multiple_choice"
    stored_corr = json.loads(q_data["correct_answer"]) if isinstance(q_data["correct_answer"], str) and q_data["correct_answer"].startswith("[") else q_data["correct_answer"]
    assert stored_corr == ["LRU", "FIFO"]
    assert q_data["partial_credit_allowed"] is True


def test_create_true_false_question(client, educator_user, sample_class):
    """Create true/false question."""
    q_resp = client.post(
        "/api/v1/quizzes",
        json={"class_id": str(sample_class.id), "title": "TF Test Quiz"},
        headers=auth_headers(educator_user),
    )
    quiz_id = q_resp.json()["id"]

    tf_payload = {
        "question_text": "Virtual memory allows an OS to address more memory than physically installed.",
        "question_type": "true_false",
        "options": ["True", "False"],
        "correct_answer": "True",
        "points": 1.0,
    }
    add_resp = client.post(
        f"/api/v1/quizzes/{quiz_id}/questions",
        json=tf_payload,
        headers=auth_headers(educator_user),
    )
    assert add_resp.status_code == 201
    q_data = add_resp.json()
    assert q_data["question_type"] == "true_false"
    assert q_data["correct_answer"] == "True"


def test_question_validation_rejections(client, educator_user, sample_class):
    """Verify robust validation and rejections:
    - Unsupported question types (numerical, subjective, free_response)
    - Duplicate options
    - Correct answer not in options
    - Fewer than 2 options
    """
    q_resp = client.post(
        "/api/v1/quizzes",
        json={"class_id": str(sample_class.id), "title": "Validation Quiz"},
        headers=auth_headers(educator_user),
    )
    quiz_id = q_resp.json()["id"]

    # 1. Unsupported question type (numerical / subjective) rejected with 400 or 422
    resp = client.post(
        f"/api/v1/quizzes/{quiz_id}/questions",
        json={
            "question_text": "Calculate the page fault rate.",
            "question_type": "numerical",
            "options": ["1"],
            "correct_answer": "1",
        },
        headers=auth_headers(educator_user),
    )
    assert resp.status_code in (400, 422)

    # 2. Duplicate options
    resp = client.post(
        f"/api/v1/quizzes/{quiz_id}/questions",
        json={
            "question_text": "Test question",
            "question_type": "single_choice",
            "options": ["Option A", "Option A"],
            "correct_answer": "Option A",
        },
        headers=auth_headers(educator_user),
    )
    assert resp.status_code == 400
    assert "duplicate" in resp.json()["detail"].lower()

    # 3. Single-choice correct answer not in options
    resp = client.post(
        f"/api/v1/quizzes/{quiz_id}/questions",
        json={
            "question_text": "Test question",
            "question_type": "single_choice",
            "options": ["Option A", "Option B"],
            "correct_answer": "Option C",
        },
        headers=auth_headers(educator_user),
    )
    assert resp.status_code == 400
    assert "does not match any of the provided options" in resp.json()["detail"].lower()

    # 4. Multi-choice correct answer empty or not in options
    resp = client.post(
        f"/api/v1/quizzes/{quiz_id}/questions",
        json={
            "question_text": "Test question",
            "question_type": "multiple_choice",
            "options": ["Option A", "Option B"],
            "correct_answer": ["Option A", "Option Missing"],
        },
        headers=auth_headers(educator_user),
    )
    assert resp.status_code == 400
    assert "does not match any of the provided options" in resp.json()["detail"].lower()


def test_question_reordering(client, educator_user, sample_class):
    """Test deterministic question reordering."""
    q_resp = client.post(
        "/api/v1/quizzes",
        json={"class_id": str(sample_class.id), "title": "Reorder Quiz"},
        headers=auth_headers(educator_user),
    )
    quiz_id = q_resp.json()["id"]

    # Add 3 questions
    q_ids = []
    for i in range(1, 4):
        resp = client.post(
            f"/api/v1/quizzes/{quiz_id}/questions",
            json={
                "question_text": f"Question {i}",
                "question_type": "single_choice",
                "options": ["A", "B"],
                "correct_answer": "A",
            },
            headers=auth_headers(educator_user),
        )
        assert resp.status_code == 201
        q_ids.append(resp.json()["id"])

    # Reverse order: [q3, q2, q1]
    rev_order = [q_ids[2], q_ids[1], q_ids[0]]
    reorder_resp = client.post(
        f"/api/v1/quizzes/{quiz_id}/reorder",
        json={"question_ids": rev_order},
        headers=auth_headers(educator_user),
    )
    assert reorder_resp.status_code == 200
    updated_questions = reorder_resp.json()
    assert updated_questions[0]["id"] == q_ids[2]
    assert updated_questions[0]["question_order"] == 1
    assert updated_questions[1]["id"] == q_ids[1]
    assert updated_questions[1]["question_order"] == 2
    assert updated_questions[2]["id"] == q_ids[0]
    assert updated_questions[2]["question_order"] == 3


def test_publish_and_archive_lifecycle(client, educator_user, sample_class):
    """Test publishing draft quiz and archiving it."""
    q_resp = client.post(
        "/api/v1/quizzes",
        json={"class_id": str(sample_class.id), "title": "Lifecycle Quiz"},
        headers=auth_headers(educator_user),
    )
    quiz_id = q_resp.json()["id"]

    # Add question
    client.post(
        f"/api/v1/quizzes/{quiz_id}/questions",
        json={
            "question_text": "Sample Q?",
            "question_type": "single_choice",
            "options": ["Yes", "No"],
            "correct_answer": "Yes",
        },
        headers=auth_headers(educator_user),
    )

    # Publish
    pub_resp = client.post(f"/api/v1/quizzes/{quiz_id}/publish", headers=auth_headers(educator_user))
    assert pub_resp.status_code == 200
    assert pub_resp.json()["status"] == "approved"

    # Archive
    arch_resp = client.post(f"/api/v1/quizzes/{quiz_id}/archive", headers=auth_headers(educator_user))
    assert arch_resp.status_code == 200
    assert arch_resp.json()["status"] == "archived"


def test_student_isolation_and_redaction(client, educator_user, student_user, sample_class, db):
    """Verify:
    1. Draft quiz is hidden from students on available list and direct fetch.
    2. Once published, student can fetch, but answer keys/explanations are redacted.
    """
    enrollment = ClassEnrollment(class_id=sample_class.id, student_id=student_user.id)
    db.add(enrollment)
    db.commit()

    # Create draft quiz
    q_resp = client.post(
        "/api/v1/quizzes",
        json={"class_id": str(sample_class.id), "title": "Secret Draft Quiz"},
        headers=auth_headers(educator_user),
    )
    quiz_id = q_resp.json()["id"]

    client.post(
        f"/api/v1/quizzes/{quiz_id}/questions",
        json={
            "question_text": "Confidential question?",
            "question_type": "single_choice",
            "options": ["A", "B"],
            "correct_answer": "A",
            "explanation": "Confidential reasoning",
        },
        headers=auth_headers(educator_user),
    )

    # 1. Student checks available quizzes -> draft NOT visible
    avail_resp = client.get(
        f"/api/v1/quizzes/available?class_id={sample_class.id}",
        headers=auth_headers(student_user),
    )
    assert avail_resp.status_code == 200
    assert not any(q["id"] == quiz_id for q in avail_resp.json())

    # Direct fetch of draft quiz by student returns 404 (draft not enrolled/approved)
    get_draft_resp = client.get(f"/api/v1/quizzes/{quiz_id}", headers=auth_headers(student_user))
    assert get_draft_resp.status_code == 404

    # 2. Publish quiz
    client.post(f"/api/v1/quizzes/{quiz_id}/publish", headers=auth_headers(educator_user))

    # Now student can fetch quiz
    pub_get_resp = client.get(f"/api/v1/quizzes/{quiz_id}", headers=auth_headers(student_user))
    assert pub_get_resp.status_code == 200
    student_view = pub_get_resp.json()
    assert len(student_view["questions"]) == 1
    sq = student_view["questions"][0]

    # Verify answers and explanations are REDACTED for student
    assert "correct_answer" not in sq
    assert "explanation" not in sq


def test_attempt_immutability_and_version_increment(client, educator_user, student_user, sample_class, db):
    """Verify:
    1. Modifying questions on an attempted quiz increments quiz.version.
    2. Deleting an attempted question or quiz is blocked.
    """
    enrollment = ClassEnrollment(class_id=sample_class.id, student_id=student_user.id)
    db.add(enrollment)
    db.commit()

    # Create & publish quiz
    q_resp = client.post(
        "/api/v1/quizzes",
        json={"class_id": str(sample_class.id), "title": "Versioned Quiz"},
        headers=auth_headers(educator_user),
    )
    quiz_id = q_resp.json()["id"]

    add_resp = client.post(
        f"/api/v1/quizzes/{quiz_id}/questions",
        json={
            "question_text": "Q1 text",
            "question_type": "single_choice",
            "options": ["A", "B"],
            "correct_answer": "A",
        },
        headers=auth_headers(educator_user),
    )
    question_id = add_resp.json()["id"]

    client.post(f"/api/v1/quizzes/{quiz_id}/publish", headers=auth_headers(educator_user))

    # Student makes an attempt
    attempt_resp = client.post(
        f"/api/v1/quizzes/{quiz_id}/attempt",
        json={"answers": {question_id: "A"}},
        headers=auth_headers(student_user),
    )
    assert attempt_resp.status_code in (200, 201)

    # Verify quiz version is currently 1
    fac_resp = client.get(f"/api/v1/quizzes/{quiz_id}/faculty", headers=auth_headers(educator_user))
    assert fac_resp.json()["version"] == 1
    assert fac_resp.json()["attempt_count"] == 1

    # Now faculty updates the question -> should increment version to 2
    update_resp = client.put(
        f"/api/v1/quizzes/questions/{question_id}",
        json={
            "question_text": "Updated Q1 text",
            "options": ["A", "B"],
            "correct_answer": "B",
        },
        headers=auth_headers(educator_user),
    )
    assert update_resp.status_code == 200

    fac_resp_after = client.get(f"/api/v1/quizzes/{quiz_id}/faculty", headers=auth_headers(educator_user))
    assert fac_resp_after.json()["version"] == 2

    # Attempting to delete the question must be blocked (HTTP 400)
    del_q_resp = client.delete(f"/api/v1/quizzes/questions/{question_id}", headers=auth_headers(educator_user))
    assert del_q_resp.status_code == 400
    assert "cannot delete question" in del_q_resp.json()["detail"].lower()

    # Attempting to delete the quiz must be blocked (HTTP 400)
    del_quiz_resp = client.delete(f"/api/v1/quizzes/{quiz_id}", headers=auth_headers(educator_user))
    assert del_quiz_resp.status_code == 400
    assert "cannot delete quiz" in del_quiz_resp.json()["detail"].lower()


def test_scoring_with_partial_credit():
    """Verify evaluate_question_answer handles single_choice, true_false, and multiple_choice partial credit."""
    q_sc = QuizQuestion(
        id=uuid.uuid4(),
        question_text="SC Q",
        question_type=QuestionType.single_choice,
        options='["A", "B", "C"]',
        correct_answer="A",
        points=2.0,
    )
    q_tf = QuizQuestion(
        id=uuid.uuid4(),
        question_text="TF Q",
        question_type=QuestionType.true_false,
        options='["True", "False"]',
        correct_answer="True",
        points=1.0,
    )
    q_mc = QuizQuestion(
        id=uuid.uuid4(),
        question_text="MC Q",
        question_type=QuestionType.multiple_choice,
        options='["A", "B", "C", "D"]',
        correct_answer='["A", "B"]',
        points=4.0,
        partial_credit_allowed=True,
    )

    # 1. Single Choice & True/False exact matching
    assert evaluate_question_answer(q_sc, "A") == (True, 1.0)
    assert evaluate_question_answer(q_sc, "B") == (False, 0.0)
    assert evaluate_question_answer(q_tf, "True") == (True, 1.0)
    assert evaluate_question_answer(q_tf, "False") == (False, 0.0)

    # 2. Multiple Choice: Full match
    assert evaluate_question_answer(q_mc, ["A", "B"]) == (True, 1.0)
    assert evaluate_question_answer(q_mc, ["B", "A"]) == (True, 1.0)

    # 3. Multiple Choice: Partial credit (1 correct out of 2, 0 incorrect)
    # (1 - 0) / 2 = 0.5 credit
    is_corr, credit = evaluate_question_answer(q_mc, ["A"])
    assert is_corr is False
    assert credit == 0.5

    # 4. Multiple Choice: Partial credit with incorrect penalty
    # 1 correct ("A") and 1 wrong ("C") out of 2: (1 - 1) / 2 = 0.0 credit
    is_corr, credit = evaluate_question_answer(q_mc, ["A", "C"])
    assert is_corr is False
    assert credit == 0.0

    # 5. Multiple Choice without partial credit allowed
    q_mc_no_partial = QuizQuestion(
        id=uuid.uuid4(),
        question_type=QuestionType.multiple_choice,
        options='["A", "B", "C"]',
        correct_answer='["A", "B"]',
        partial_credit_allowed=False,
    )
    assert evaluate_question_answer(q_mc_no_partial, ["A", "B"]) == (True, 1.0)
    assert evaluate_question_answer(q_mc_no_partial, ["A"]) == (False, 0.0)
