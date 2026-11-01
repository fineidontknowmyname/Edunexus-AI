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
    QuestionType,
    Quiz,
    QuizAttempt,
    QuizAttemptAnswer,
    QuizCoverageReport,
    QuizQuestion,
    ReviewStatus,
    Subject,
    SyllabusSubtopic,
    TopicMastery,
    User,
    UserRole,
)
from backend.services.quiz_service import score_attempt
from backend.tests.conftest import auth_headers

TEST_UNIT_5 = 88


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
def mapped_quiz_fixture(client, educator_user, student_user, sample_class, db):
    """Creates an approved quiz with single-choice, multi-choice (partial credit),
    and true-false questions mapped to a real topic, plus one unmapped question.
    """
    enrollment = ClassEnrollment(class_id=sample_class.id, student_id=student_user.id)
    db.add(enrollment)

    subject = db.query(Subject).first()
    topic = PrerequisiteMap(
        subject_id=subject.id,
        subject=subject.name,
        topic=f"P5-Topic-{uuid.uuid4().hex[:6]}",
        unit=TEST_UNIT_5,
        order_index=1,
        is_canonical=True,
        created_by=educator_user.id,
    )
    db.add(topic)
    db.commit()

    # Create quiz
    q_resp = client.post(
        "/api/v1/quizzes",
        json={"class_id": str(sample_class.id), "title": "P5 Assessment Quiz", "unit": TEST_UNIT_5},
        headers=auth_headers(educator_user),
    )
    quiz_id = q_resp.json()["id"]

    # Q1: Single-choice (2 points, mapped to topic)
    resp1 = client.post(
        f"/api/v1/quizzes/{quiz_id}/questions",
        json={
            "question_text": "Q1 SC Question",
            "question_type": "single_choice",
            "options": ["A", "B", "C"],
            "correct_answer": "A",
            "points": 2.0,
            "topic_id": str(topic.id),
        },
        headers=auth_headers(educator_user),
    )
    q1_id = resp1.json()["id"]

    # Q2: Multi-choice (4 points, partial credit allowed, mapped to topic)
    resp2 = client.post(
        f"/api/v1/quizzes/{quiz_id}/questions",
        json={
            "question_text": "Q2 MC Question",
            "question_type": "multiple_choice",
            "options": ["Opt1", "Opt2", "Opt3", "Opt4"],
            "correct_answer": ["Opt1", "Opt2"],
            "points": 4.0,
            "partial_credit_allowed": True,
            "topic_id": str(topic.id),
        },
        headers=auth_headers(educator_user),
    )
    q2_id = resp2.json()["id"]

    # Q3: True/False (1 point, mapped to topic)
    resp3 = client.post(
        f"/api/v1/quizzes/{quiz_id}/questions",
        json={
            "question_text": "Q3 TF Question",
            "question_type": "true_false",
            "options": ["True", "False"],
            "correct_answer": "True",
            "points": 1.0,
            "topic_id": str(topic.id),
        },
        headers=auth_headers(educator_user),
    )
    q3_id = resp3.json()["id"]

    # Q4: Unmapped question (1 point, no topic)
    resp4 = client.post(
        f"/api/v1/quizzes/{quiz_id}/questions",
        json={
            "question_text": "Q4 Unmapped Question",
            "question_type": "single_choice",
            "options": ["Yes", "No"],
            "correct_answer": "Yes",
            "points": 1.0,
        },
        headers=auth_headers(educator_user),
    )
    q4_id = resp4.json()["id"]

    # Publish quiz
    client.post(f"/api/v1/quizzes/{quiz_id}/publish", headers=auth_headers(educator_user))

    return {
        "quiz_id": quiz_id,
        "topic": topic,
        "q1_id": q1_id,
        "q2_id": q2_id,
        "q3_id": q3_id,
        "q4_id": q4_id,
    }


def test_assessment_submission_lifecycle(client, student_user, sample_class, mapped_quiz_fixture, db):
    """Verify:
    1. Score calculation with partial credit on multi-choice.
    2. Answers persisted in quiz_attempt_answers.
    3. TopicMastery updated for the mapped topic.
    4. TopicMastery NOT updated for unmapped/General topics.
    """
    quiz_id = mapped_quiz_fixture["quiz_id"]
    topic_name = mapped_quiz_fixture["topic"].topic

    # Student answers:
    # Q1: Correct ("A") -> 2.0 points
    # Q2: Partial (chose ["Opt1"] out of ["Opt1", "Opt2"]) -> 50% credit = 2.0 points out of 4.0
    # Q3: Correct ("True") -> 1.0 point
    # Q4: Correct ("Yes") -> 1.0 point
    # Total earned: 2.0 + 2.0 + 1.0 + 1.0 = 6.0 points out of 8.0 max = 75.0%
    sub_payload = {
        "answers": {
            mapped_quiz_fixture["q1_id"]: "A",
            mapped_quiz_fixture["q2_id"]: ["Opt1"],
            mapped_quiz_fixture["q3_id"]: "True",
            mapped_quiz_fixture["q4_id"]: "Yes",
        }
    }
    resp = client.post(f"/api/v1/quizzes/{quiz_id}/attempt", json=sub_payload, headers=auth_headers(student_user))
    assert resp.status_code == 201
    data = resp.json()

    assert data["score"] == 75.0
    attempt_id = data["attempt_id"]

    # Verify per-question persisted answer rows
    answers_in_db = (
        db.query(QuizAttemptAnswer)
        .filter(QuizAttemptAnswer.attempt_id == uuid.UUID(attempt_id))
        .all()
    )
    assert len(answers_in_db) == 4
    for ans in answers_in_db:
        assert ans.class_id == sample_class.id
        assert ans.student_id == student_user.id

    # Verify TopicMastery was updated for topic_name
    mastery_row = (
        db.query(TopicMastery)
        .filter(TopicMastery.student_id == student_user.id, TopicMastery.topic == topic_name)
        .first()
    )
    assert mastery_row is not None
    # For topic_name: Q1 (2.0/2.0), Q2 (2.0/4.0), Q3 (1.0/1.0) -> 5.0/7.0 points = 0.714
    assert 0.70 <= mastery_row.mastery_score <= 0.73

    # Verify NO TopicMastery was created for "General" or "Unmapped"
    general_mastery = (
        db.query(TopicMastery)
        .filter(TopicMastery.student_id == student_user.id, TopicMastery.topic.in_(["General", "Unmapped"]))
        .first()
    )
    assert general_mastery is None


def test_submission_rejection_invalid_questions_and_duplicates(client, student_user, mapped_quiz_fixture):
    """Verify:
    1. Answers with invalid question IDs are rejected with HTTP 400.
    2. Submitting duplicate identical attempt within duplicate window is rejected with HTTP 409.
    """
    quiz_id = mapped_quiz_fixture["quiz_id"]

    # 1. Foreign question ID
    foreign_id = str(uuid.uuid4())
    bad_payload = {
        "answers": {
            foreign_id: "Option A",
        }
    }
    bad_resp = client.post(f"/api/v1/quizzes/{quiz_id}/attempt", json=bad_payload, headers=auth_headers(student_user))
    assert bad_resp.status_code == 400
    assert "does not belong to this quiz" in bad_resp.json()["detail"].lower()

    # 2. Duplicate submission
    good_payload = {
        "answers": {
            mapped_quiz_fixture["q1_id"]: "A",
        }
    }
    first_resp = client.post(f"/api/v1/quizzes/{quiz_id}/attempt", json=good_payload, headers=auth_headers(student_user))
    assert first_resp.status_code == 201

    # Immediate identical second submission
    dup_resp = client.post(f"/api/v1/quizzes/{quiz_id}/attempt", json=good_payload, headers=auth_headers(student_user))
    assert dup_resp.status_code == 409
    assert "already received" in dup_resp.json()["detail"].lower()


def test_attempt_history_and_student_isolation(client, student_user, student_user_2, mapped_quiz_fixture):
    """Verify:
    1. Student retrieves their attempts via /attempts/mine and /attempts/{id}.
    2. Other students cannot access the attempt (isolation).
    """
    quiz_id = mapped_quiz_fixture["quiz_id"]
    sub_payload = {"answers": {mapped_quiz_fixture["q1_id"]: "A"}}
    att_resp = client.post(f"/api/v1/quizzes/{quiz_id}/attempt", json=sub_payload, headers=auth_headers(student_user))
    assert att_resp.status_code == 201
    attempt_id = att_resp.json()["attempt_id"]

    # Student 1 fetches their attempts list
    mine_resp = client.get("/api/v1/quizzes/attempts/mine", headers=auth_headers(student_user))
    assert mine_resp.status_code == 200
    mine = mine_resp.json()
    assert any(a["id"] == attempt_id for a in mine)

    # Student 1 fetches attempt detail
    det_resp = client.get(f"/api/v1/quizzes/attempts/{attempt_id}", headers=auth_headers(student_user))
    assert det_resp.status_code == 200
    det = det_resp.json()
    assert det["id"] == attempt_id
    assert det["quiz_title"] == "P5 Assessment Quiz"
    assert det["quiz_version"] == 1
    assert len(det["answers"]) == 4

    # Student 2 tries to access Student 1's attempt -> 404
    foreign_resp = client.get(f"/api/v1/quizzes/attempts/{attempt_id}", headers=auth_headers(student_user_2))
    assert foreign_resp.status_code == 404
