import uuid
import pytest
from backend.core.database import SessionLocal
from backend.models.db import (
    Class,
    CoverageStatus,
    Document,
    DocumentStatus,
    LearningObjective,
    PrerequisiteMap,
    QuestionCurriculumMapping,
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
from backend.services.coverage_service import analyze_quiz_coverage, acknowledge_coverage_warnings
from backend.tests.conftest import auth_headers

TEST_UNIT = 99


@pytest.fixture(autouse=True)
def cleanup_quiz_database(db, sample_class, educator_user):
    """Ensure all test quizzes, attempts, questions, and curriculum records are wiped
    before and after each test to prevent foreign key errors during user/class teardown.
    """
    def _cleanup():
        db.rollback()
        db.query(QuizAttemptAnswer).filter(QuizAttemptAnswer.class_id == sample_class.id).delete()
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
def multi_topic_curriculum(db, educator_user, sample_class):
    """Creates Subject with two topics, subtopics, and objectives in TEST_UNIT."""
    subject = db.query(Subject).first()
    assert subject is not None, "Subject must exist in database"
    sample_class.subject_id = subject.id
    db.commit()

    # Topic 1: Process Scheduling (2 subtopics)
    topic1 = PrerequisiteMap(
        subject_id=subject.id,
        subject=subject.name,
        topic=f"Topic-1-{uuid.uuid4().hex[:6]}",
        unit=TEST_UNIT,
        order_index=1,
        is_canonical=True,
        created_by=educator_user.id,
    )
    db.add(topic1)
    db.flush()

    sub1_1 = SyllabusSubtopic(topic_id=topic1.id, name="CPU Scheduling", order_index=1)
    sub1_2 = SyllabusSubtopic(topic_id=topic1.id, name="Thread Scheduling", order_index=2)
    db.add_all([sub1_1, sub1_2])
    db.flush()

    obj1_1 = LearningObjective(topic_id=topic1.id, subtopic_id=sub1_1.id, statement="Explain Round Robin")
    db.add(obj1_1)
    db.flush()

    # Topic 2: Virtual Memory (1 subtopic)
    topic2 = PrerequisiteMap(
        subject_id=subject.id,
        subject=subject.name,
        topic=f"Topic-2-{uuid.uuid4().hex[:6]}",
        unit=TEST_UNIT,
        order_index=2,
        is_canonical=True,
        created_by=educator_user.id,
    )
    db.add(topic2)
    db.flush()

    sub2_1 = SyllabusSubtopic(topic_id=topic2.id, name="Page Replacement", order_index=1)
    db.add(sub2_1)
    db.flush()

    db.commit()

    yield {
        "subject": subject,
        "topic1": topic1,
        "sub1_1": sub1_1,
        "sub1_2": sub1_2,
        "obj1_1": obj1_1,
        "topic2": topic2,
        "sub2_1": sub2_1,
    }


def test_coverage_analysis_engine(client, educator_user, sample_class, multi_topic_curriculum, db):
    """Verify coverage calculation identifies covered, partially covered, not covered, and unmapped questions."""
    # Create quiz scoped to TEST_UNIT
    q_resp = client.post(
        "/api/v1/quizzes",
        json={"class_id": str(sample_class.id), "title": "Coverage Test Quiz", "unit": TEST_UNIT},
        headers=auth_headers(educator_user),
    )
    assert q_resp.status_code == 201
    quiz_id = q_resp.json()["id"]

    # Add Question 1: Mapped to Topic 1, Subtopic 1_1, Obj 1_1
    client.post(
        f"/api/v1/quizzes/{quiz_id}/questions",
        json={
            "question_text": "What is Round Robin?",
            "question_type": "single_choice",
            "options": ["Preemptive", "Non-preemptive"],
            "correct_answer": "Preemptive",
            "topic_id": str(multi_topic_curriculum["topic1"].id),
            "subtopic_id": str(multi_topic_curriculum["sub1_1"].id),
            "objective_id": str(multi_topic_curriculum["obj1_1"].id),
        },
        headers=auth_headers(educator_user),
    )

    # Add Question 2: Unmapped question
    client.post(
        f"/api/v1/quizzes/{quiz_id}/questions",
        json={
            "question_text": "What is hardware?",
            "question_type": "single_choice",
            "options": ["Physical", "Software"],
            "correct_answer": "Physical",
        },
        headers=auth_headers(educator_user),
    )

    # Fetch coverage report
    cov_resp = client.get(f"/api/v1/quizzes/{quiz_id}/coverage", headers=auth_headers(educator_user))
    assert cov_resp.status_code == 200
    cov = cov_resp.json()

    assert cov["total_questions"] == 2
    assert cov["mapped_questions"] == 1
    assert len(cov["unmapped_questions"]) == 1
    assert cov["unmapped_questions"][0]["question_text"] == "What is hardware?"

    # Matrix checks:
    # Topic 1 has 2 subtopics, only sub1_1 is mapped -> partially_covered
    # Topic 2 has 0 questions mapped -> not_covered
    matrix = {row["topic_id"]: row for row in cov["coverage_matrix"]}
    t1_row = matrix[str(multi_topic_curriculum["topic1"].id)]
    t2_row = matrix[str(multi_topic_curriculum["topic2"].id)]

    assert t1_row["status"] == "partially_covered"
    assert t1_row["covered_subtopics"] == 1
    assert t1_row["total_subtopics"] == 2

    assert t2_row["status"] == "not_covered"
    assert t2_row["question_count"] == 0

    # Warnings check
    warning_codes = [w["code"] for w in cov["warnings"]]
    assert "UNMAPPED_QUESTIONS" in warning_codes
    assert "TOPIC_NOT_COVERED" in warning_codes

    # Verify coverage snapshot persisted in DB
    report_db = db.query(QuizCoverageReport).filter(QuizCoverageReport.quiz_id == uuid.UUID(quiz_id)).first()
    assert report_db is not None
    assert report_db.total_topics == 2


def test_coverage_is_advisory_and_publishing_unblocked(client, educator_user, sample_class, multi_topic_curriculum):
    """Verify advisory warnings DO NOT block publishing."""
    q_resp = client.post(
        "/api/v1/quizzes",
        json={"class_id": str(sample_class.id), "title": "Advisory Quiz", "unit": TEST_UNIT},
        headers=auth_headers(educator_user),
    )
    quiz_id = q_resp.json()["id"]

    # Add question mapped only to Topic 1 (Topic 2 remains unassessed)
    client.post(
        f"/api/v1/quizzes/{quiz_id}/questions",
        json={
            "question_text": "Sample Q?",
            "question_type": "single_choice",
            "options": ["A", "B"],
            "correct_answer": "A",
            "topic_id": str(multi_topic_curriculum["topic1"].id),
        },
        headers=auth_headers(educator_user),
    )

    # Coverage has warning for Topic 2
    cov_resp = client.get(f"/api/v1/quizzes/{quiz_id}/coverage", headers=auth_headers(educator_user))
    assert cov_resp.status_code == 200
    assert len(cov_resp.json()["warnings"]) > 0

    # Publish succeeds without error
    pub_resp = client.post(f"/api/v1/quizzes/{quiz_id}/publish", headers=auth_headers(educator_user))
    assert pub_resp.status_code == 200
    assert pub_resp.json()["status"] == "approved"


def test_coverage_recalculation_and_acknowledgment(client, educator_user, sample_class, multi_topic_curriculum):
    """Verify recalculation updates matrix and acknowledge records notes."""
    q_resp = client.post(
        "/api/v1/quizzes",
        json={"class_id": str(sample_class.id), "title": "Recalc Quiz", "unit": TEST_UNIT},
        headers=auth_headers(educator_user),
    )
    quiz_id = q_resp.json()["id"]

    # Add Q1 for Topic 1
    client.post(
        f"/api/v1/quizzes/{quiz_id}/questions",
        json={
            "question_text": "Q1 text",
            "question_type": "single_choice",
            "options": ["A", "B"],
            "correct_answer": "A",
            "topic_id": str(multi_topic_curriculum["topic1"].id),
        },
        headers=auth_headers(educator_user),
    )

    # Coverage before adding Q2
    cov1 = client.get(f"/api/v1/quizzes/{quiz_id}/coverage", headers=auth_headers(educator_user)).json()
    assert cov1["covered_topics"] + cov1["partially_covered_topics"] == 1

    # Add Q2 for Topic 2
    client.post(
        f"/api/v1/quizzes/{quiz_id}/questions",
        json={
            "question_text": "Q2 text",
            "question_type": "single_choice",
            "options": ["A", "B"],
            "correct_answer": "A",
            "topic_id": str(multi_topic_curriculum["topic2"].id),
            "subtopic_id": str(multi_topic_curriculum["sub2_1"].id),
        },
        headers=auth_headers(educator_user),
    )

    # Recalculate coverage
    recalc_resp = client.post(f"/api/v1/quizzes/{quiz_id}/coverage/recalculate", headers=auth_headers(educator_user))
    assert recalc_resp.status_code == 200
    cov2 = recalc_resp.json()
    assert cov2["total_questions"] == 2
    assert cov2["missing_topics"] == 0

    # Acknowledge warnings
    ack_resp = client.post(
        f"/api/v1/quizzes/{quiz_id}/coverage/acknowledge",
        json={"faculty_notes": "Reviewed and confirmed adequate for Unit 99 quiz."},
        headers=auth_headers(educator_user),
    )
    assert ack_resp.status_code == 200
    assert ack_resp.json()["faculty_acknowledged"] is True
    assert ack_resp.json()["faculty_notes"] == "Reviewed and confirmed adequate for Unit 99 quiz."
