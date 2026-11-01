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
def cleanup_e2e_data(db: Session, sample_class: Class, educator_user: User, student_user: User, student_user_2: User):
    def _cleanup():
        db.rollback()
        # Clean quizzes and attempts created in this class
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
def e2e_environment(cleanup_e2e_data, db: Session, sample_class: Class, educator_user: User, student_user: User):
    """Sets up an end-to-end curriculum environment with documents, chunks, and initial student mastery."""
    # Enroll student in class
    enrollment = ClassEnrollment(
        class_id=sample_class.id,
        student_id=student_user.id,
    )
    db.add(enrollment)

    # Category setup
    cat = db.query(Category).first()
    if not cat:
        cat = Category(name=f"BioCategory-{uuid.uuid4().hex[:4]}", created_by=educator_user.id)
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

    # Document 1: Main Syllabus & Textbook
    doc1 = Document(
        title="Cellular Energy and Metabolism",
        filename="cell_metabolism.pdf",
        status=DocumentStatus.ready,
        is_indexed=True,
        chunk_count=2,
        class_id=sample_class.id,
        subject_id=subject.id,
        uploaded_by_id=educator_user.id,
    )
    db.add(doc1)
    db.flush()

    # Canonical Topic 1: Glycolytic Pathway (Weak topic)
    topic_glycolysis = PrerequisiteMap(
        subject_id=subject.id,
        subject=subject.name,
        topic="Glycolytic Pathway",
        description="Enzymatic breakdown of glucose to pyruvate yielding ATP and NADH.",
        unit=2,
        order_index=1,
        is_canonical=True,
        source_document_id=doc1.id,
        source_page_number=35,
        created_by=educator_user.id,
    )
    # Canonical Topic 2: Photosynthesis (Unrelated topic)
    topic_photo = PrerequisiteMap(
        subject_id=subject.id,
        subject=subject.name,
        topic="Light-Dependent Reactions",
        description="Thylakoid membrane reactions producing ATP and NADPH from solar photons.",
        unit=4,
        order_index=2,
        is_canonical=True,
        source_document_id=doc1.id,
        source_page_number=80,
        created_by=educator_user.id,
    )
    db.add_all([topic_glycolysis, topic_photo])
    db.flush()

    # Chunks for Glycolytic Pathway
    chunk1 = Chunk(
        document_id=doc1.id,
        class_id=sample_class.id,
        subject_id=subject.id,
        subject=subject.name,
        topic="Glycolytic Pathway",
        page_number=35,
        chunk_index=0,
        token_count=130,
        section_heading="Energy Investment Phase",
        text=(
            "Hexokinase and phosphofructokinase-1 consume two ATP molecules to phosphorylate glucose "
            "into fructose 1,6-bisphosphate, priming it for cleavage into two three-carbon trioses."
        ),
        contextual_prefix="Chapter 2: Glycolysis",
        full_text="Hexokinase and phosphofructokinase-1 consume two ATP molecules to phosphorylate glucose.",
        embedding=[0.05] * 384,
    )

    chunk2 = Chunk(
        document_id=doc1.id,
        class_id=sample_class.id,
        subject_id=subject.id,
        subject=subject.name,
        topic="Glycolytic Pathway",
        page_number=38,
        chunk_index=1,
        token_count=145,
        section_heading="Energy Generation and Net Yield",
        text=(
            "In the payoff phase of the glycolytic pathway, substrate-level phosphorylation produces four ATP "
            "and two NADH molecules per glucose, resulting in a net yield of two ATP molecules and two pyruvate molecules."
        ),
        contextual_prefix="Chapter 2: Glycolysis",
        full_text="Substrate-level phosphorylation yields four ATP and two NADH, net gain of two ATP.",
        embedding=[0.06] * 384,
    )
    db.add_all([chunk1, chunk2])

    # Initial Student Mastery Records:
    # 1. Glycolytic Pathway: Low score 0.35 with sufficient evidence (weak topic recommendation candidate)
    mastery_glycolysis = TopicMastery(
        student_id=student_user.id,
        class_id=sample_class.id,
        subject_id=subject.id,
        topic="Glycolytic Pathway",
        mastery_score=0.35,
        attempt_count=2,
        mastery_v2=json.dumps({
            "overall_score": 0.35,
            "evidence_state": "sufficient",
            "mastery_band": "low",
            "assessment_count": 2,
        }),
    )
    # 2. Light-Dependent Reactions: Strong score 0.85 (should remain untouched)
    mastery_photo = TopicMastery(
        student_id=student_user.id,
        class_id=sample_class.id,
        subject_id=subject.id,
        topic="Light-Dependent Reactions",
        mastery_score=0.85,
        attempt_count=3,
        mastery_v2=json.dumps({
            "overall_score": 0.85,
            "evidence_state": "sufficient",
            "mastery_band": "high",
            "assessment_count": 3,
        }),
    )
    db.add_all([mastery_glycolysis, mastery_photo])
    db.commit()

    return {
        "subject": subject,
        "doc1": doc1,
        "topic_glycolysis": topic_glycolysis,
        "topic_photo": topic_photo,
        "chunk1": chunk1,
        "chunk2": chunk2,
        "mastery_glycolysis": mastery_glycolysis,
        "mastery_photo": mastery_photo,
    }


# ==============================================================================
# Complete 6-Step End-to-End Student Workflow Test
# ==============================================================================

def test_full_topic_quiz_lifecycle_e2e(client, db: Session, sample_class: Class, student_user: User, e2e_environment):
    """Verifies the complete 6-step lifecycle:
    Step 1: Weak-topic discovery via progress recommendations.
    Step 2: Learn the concept resource access without mastery side-effects.
    Step 3: Take a Test generation with structured grounding & provenance.
    Step 4: Quiz runner rendering without premature answer leakage.
    Step 5: Assessment submission, scoring, explanations, and partial credit.
    Step 6: Targeted topic mastery update, preserving unrelated topics.
    """
    topic_g = e2e_environment["topic_glycolysis"]
    topic_p = e2e_environment["topic_photo"]

    # --------------------------------------------------------------------------
    # Step 1: Weak-topic discovery
    # --------------------------------------------------------------------------
    rec_resp = client.get(
        f"/api/v1/progress/recommendations?class_id={sample_class.id}",
        headers=auth_headers(student_user),
    )
    assert rec_resp.status_code == 200, rec_resp.text
    rec_data = rec_resp.json()

    # Verify weak topic is present and targeted
    weak_topics = [r["topic"] for r in (rec_data.get("weak_topics") or rec_data.get("recommendations", []))]
    assert "Glycolytic Pathway" in weak_topics
    assert topic_g.subject_id == sample_class.subject_id

    # --------------------------------------------------------------------------
    # Step 2: Learn the Concept Interaction (No Mastery Side-Effects)
    # --------------------------------------------------------------------------
    res_resp = client.get(
        f"/api/v1/resources?class_id={sample_class.id}&topic=Glycolytic+Pathway",
        headers=auth_headers(student_user),
    )
    assert res_resp.status_code == 200
    assert isinstance(res_resp.json(), list)

    # Verify that reading resources produced NO side-effect on TopicMastery
    m_check = db.query(TopicMastery).filter(
        TopicMastery.student_id == student_user.id,
        TopicMastery.topic == "Glycolytic Pathway",
    ).first()
    assert m_check.mastery_score == 0.35
    assert m_check.attempt_count == 2

    # --------------------------------------------------------------------------
    # Step 3: Take a Test (Topic Practice Quiz Generation)
    # --------------------------------------------------------------------------
    mock_candidates = [
        {
            "question": "Which enzyme consumes ATP during the initial phase of the glycolytic pathway?",
            "question_type": "single_choice",
            "options": ["Hexokinase", "Pyruvate Kinase", "Enolase", "Aldolase"],
            "correct_answer": "Hexokinase",
            "difficulty": "easy",
            "bloom_level": "remember",
            "explanation": "Hexokinase consumes ATP to phosphorylate glucose.",
            "chunk_index": 1,
        },
        {
            "question": "What is the net gain of ATP molecules produced per glucose during the glycolytic pathway?",
            "question_type": "single_choice",
            "options": ["2 ATP", "4 ATP", "32 ATP", "0 ATP"],
            "correct_answer": "2 ATP",
            "difficulty": "medium",
            "bloom_level": "understand",
            "explanation": "Four ATP are produced but two are consumed, yielding a net gain of 2 ATP.",
            "chunk_index": 2,
        },
        {
            "question": "Substrate-level phosphorylation in the payoff phase generates both ATP and NADH.",
            "question_type": "true_false",
            "options": ["True", "False"],
            "correct_answer": "True",
            "difficulty": "medium",
            "bloom_level": "understand",
            "explanation": "The payoff phase generates four ATP and two NADH per glucose molecule.",
            "chunk_index": 2,
        },
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
                "topic": topic_g.topic,
                "topic_id": str(topic_g.id),
                "num_questions": 3,
            },
        )

    assert gen_resp.status_code == 201, gen_resp.text
    gen_data = gen_resp.json()
    quiz_id = gen_data["quiz_id"]
    assert gen_data["question_count"] == 3
    assert gen_data["status"] == "approved"

    # --------------------------------------------------------------------------
    # Step 4: Quiz Execution & Sanitization
    # --------------------------------------------------------------------------
    runner_resp = client.get(
        f"/api/v1/quizzes/{quiz_id}",
        headers=auth_headers(student_user),
    )
    assert runner_resp.status_code == 200
    runner_data = runner_resp.json()
    assert runner_data["id"] == quiz_id
    assert len(runner_data["questions"]) == 3

    # Academic integrity: verify answer keys and explanations are completely sanitized
    for q_item in runner_data["questions"]:
        assert "correct_answer" not in q_item
        assert "explanation" not in q_item
        assert len(q_item["options"]) >= 2

    # Verify that opening the runner did NOT count as an attempt
    m_check2 = db.query(TopicMastery).filter(
        TopicMastery.student_id == student_user.id,
        TopicMastery.topic == "Glycolytic Pathway",
    ).first()
    assert m_check2.mastery_score == 0.35
    assert m_check2.attempt_count == 2

    # --------------------------------------------------------------------------
    # Step 5: Submission, Scoring & Results Review
    # --------------------------------------------------------------------------
    q_map = {q["question_order"]: q["id"] for q in runner_data["questions"]}

    # Student answers Q1 correctly, Q2 correctly, and Q3 incorrectly
    attempt_payload = {
        "answers": {
            q_map[1]: "Hexokinase",
            q_map[2]: "2 ATP",
            q_map[3]: "False",  # Correct is True
        }
    }

    sub_resp = client.post(
        f"/api/v1/quizzes/{quiz_id}/attempt",
        headers=auth_headers(student_user),
        json=attempt_payload,
    )
    assert sub_resp.status_code == 201, sub_resp.text
    sub_data = sub_resp.json()
    attempt_id = sub_data["attempt_id"]
    # 2 out of 3 correct = 66.67%
    assert 66.0 <= sub_data["score"] <= 67.0
    assert "Glycolytic Pathway" in sub_data["topic_scores"]

    # Student inspects detailed attempt feedback
    detail_resp = client.get(
        f"/api/v1/quizzes/attempts/{attempt_id}",
        headers=auth_headers(student_user),
    )
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert detail_data["id"] == attempt_id
    assert len(detail_data["answers"]) == 3

    # Detailed scoring and correctness revealed upon submission
    assert "results" in sub_data
    for res_item in sub_data["results"]:
        assert "correct" in res_item
        assert "correct_answer" in res_item
        assert "chosen" in res_item
        assert "credit_fraction" in res_item

    # Stored attempt answers confirm question-level correctness
    for ans_item in detail_data["answers"]:
        assert "is_correct" in ans_item
        assert ans_item["topic"] == "Glycolytic Pathway"

    # --------------------------------------------------------------------------
    # Step 6: Mastery Update & Unrelated Topic Protection
    # --------------------------------------------------------------------------
    db.expire_all()
    updated_glycolysis = db.query(TopicMastery).filter(
        TopicMastery.student_id == student_user.id,
        TopicMastery.topic == "Glycolytic Pathway",
    ).first()
    assert updated_glycolysis.attempt_count == 1
    # Authoritative calculation from QuizAttempt history: score is updated to 0.667
    assert updated_glycolysis.mastery_score == 0.667

    # Crucial check: unrelated topic (Photosynthesis) remained completely unchanged
    unaffected_photo = db.query(TopicMastery).filter(
        TopicMastery.student_id == student_user.id,
        TopicMastery.topic == "Light-Dependent Reactions",
    ).first()
    assert unaffected_photo.mastery_score == 0.85
    assert unaffected_photo.attempt_count == 3


# ==============================================================================
# Comprehensive Data Integrity Audit
# ==============================================================================

def test_data_integrity_audit(client, db: Session, sample_class: Class, student_user: User, e2e_environment):
    """Audits database records before and after practice quiz generation:
    1. Foreign keys point to valid Class, Document, Chunk, and User records.
    2. QuestionCurriculumMapping preserves topic_id and bloom_level.
    3. Quiz.description holds valid audit telemetry JSON.
    4. Zero orphaned records or partial transactions exist.
    """
    topic_g = e2e_environment["topic_glycolysis"]
    doc1 = e2e_environment["doc1"]

    mock_candidates = [
        {
            "question": "Which enzyme converts glucose to glucose-6-phosphate?",
            "question_type": "single_choice",
            "options": ["Hexokinase", "Phosphofructokinase-1", "Aldolase", "Enolase"],
            "correct_answer": "Hexokinase",
            "difficulty": "easy",
            "bloom_level": "remember",
            "explanation": "Hexokinase performs the initial phosphorylation.",
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
                "topic": topic_g.topic,
                "topic_id": str(topic_g.id),
                "num_questions": 1,
            },
        )

    assert gen_resp.status_code == 201
    quiz_id = uuid.UUID(gen_resp.json()["quiz_id"])

    # 1. Audit Quiz record
    quiz_row = db.get(Quiz, quiz_id)
    assert quiz_row is not None
    assert quiz_row.class_id == sample_class.id
    assert quiz_row.created_by_id == student_user.id
    assert quiz_row.document_id == doc1.id
    assert quiz_row.generation_type == "topic_practice"

    # Audit JSON telemetry in description
    telemetry = json.loads(quiz_row.description)
    assert telemetry["type"] == "topic_practice"
    assert telemetry["canonical_topic"] == "Glycolytic Pathway"
    assert telemetry["prompt_version"] == "v3.0-grounded-diversity"
    assert telemetry["accepted_count"] == 1

    # 2. Audit QuizQuestion records
    q_row = quiz_row.questions[0]
    assert q_row.quiz_id == quiz_row.id
    assert q_row.topic == "Glycolytic Pathway"
    assert q_row.topic_id == topic_g.id
    assert q_row.source_document_id == doc1.id
    assert q_row.source_chunk_id is not None
    assert q_row.source_page_number in {35, 38}

    # 3. Audit QuestionCurriculumMapping
    mapping = db.query(QuestionCurriculumMapping).filter(
        QuestionCurriculumMapping.question_id == q_row.id
    ).first()
    assert mapping is not None
    assert mapping.topic_id == topic_g.id
    assert mapping.bloom_level == "remember"
    assert mapping.weight == 1.0

    # 4. Check for orphan questions
    orphans = db.query(QuizQuestion).filter(QuizQuestion.quiz_id == None).count()  # noqa: E711
    assert orphans == 0


# ==============================================================================
# Negative & Failure-Path Security Tests
# ==============================================================================

def test_failure_paths_and_security(client, db: Session, sample_class: Class, student_user: User, student_user_2: User, e2e_environment):
    """Exhaustively tests failure paths, access control, and adversarial inputs:
    - Unauthenticated request
    - Unauthorized class access
    - Foreign subject topic ID
    - Submitting foreign question IDs
    - Repeated submission race condition
    - Cross-student practice quiz isolation
    """
    topic_g = e2e_environment["topic_glycolysis"]

    # 1. Unauthenticated request -> 401
    unauth_resp = client.post(
        "/api/v1/quizzes/topic-quiz",
        json={
            "class_id": str(sample_class.id),
            "topic": topic_g.topic,
            "topic_id": str(topic_g.id),
            "num_questions": 3,
        },
    )
    assert unauth_resp.status_code in (401, 403)

    # 2. Non-enrolled student request -> 404
    not_enrolled_resp = client.post(
        "/api/v1/quizzes/topic-quiz",
        headers=auth_headers(student_user_2),
        json={
            "class_id": str(sample_class.id),
            "topic": topic_g.topic,
            "topic_id": str(topic_g.id),
            "num_questions": 3,
        },
    )
    assert not_enrolled_resp.status_code == 404

    # 3. Non-existent topic ID -> 400
    fake_id = str(uuid.uuid4())
    fake_topic_resp = client.post(
        "/api/v1/quizzes/topic-quiz",
        headers=auth_headers(student_user),
        json={
            "class_id": str(sample_class.id),
            "topic": "Non Existent",
            "topic_id": fake_id,
            "num_questions": 3,
        },
    )
    assert fake_topic_resp.status_code == 400
    assert "not found" in fake_topic_resp.json()["detail"].lower()

    # 4. Generate valid quiz for student 1
    mock_candidates = [
        {
            "question": "What is the net yield of ATP in the glycolytic pathway?",
            "question_type": "single_choice",
            "options": ["2 ATP", "4 ATP", "8 ATP", "10 ATP"],
            "correct_answer": "2 ATP",
            "difficulty": "medium",
            "bloom_level": "understand",
            "explanation": "Net gain of 2 ATP.",
            "chunk_index": 2,
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
                "topic": topic_g.topic,
                "topic_id": str(topic_g.id),
                "num_questions": 1,
            },
        )
    quiz_id = gen_resp.json()["quiz_id"]

    # 5. Cross-student access rejection:
    # Enroll student 2 in the class
    db.add(ClassEnrollment(class_id=sample_class.id, student_id=student_user_2.id))
    db.commit()

    # Student 2 tries to read Student 1's practice quiz -> 404
    s2_read = client.get(
        f"/api/v1/quizzes/{quiz_id}",
        headers=auth_headers(student_user_2),
    )
    assert s2_read.status_code == 404

    # Student 2 tries to submit attempt for Student 1's practice quiz -> 404
    s2_sub = client.post(
        f"/api/v1/quizzes/{quiz_id}/attempt",
        headers=auth_headers(student_user_2),
        json={"answers": {str(uuid.uuid4()): "2 ATP"}},
    )
    assert s2_sub.status_code == 404

    # 6. Foreign question ID in student 1 submission -> 400
    foreign_qid = str(uuid.uuid4())
    foreign_sub = client.post(
        f"/api/v1/quizzes/{quiz_id}/attempt",
        headers=auth_headers(student_user),
        json={"answers": {foreign_qid: "2 ATP"}},
    )
    assert foreign_sub.status_code == 400
    assert "does not belong" in foreign_sub.json()["detail"].lower()

    # 7. Valid submission by student 1
    runner_data = client.get(f"/api/v1/quizzes/{quiz_id}", headers=auth_headers(student_user)).json()
    valid_qid = runner_data["questions"][0]["id"]
    valid_sub = client.post(
        f"/api/v1/quizzes/{quiz_id}/attempt",
        headers=auth_headers(student_user),
        json={"answers": {valid_qid: "2 ATP"}},
    )
    assert valid_sub.status_code == 201

    # 8. Duplicate submission within 30 seconds -> 409 Conflict
    dup_sub = client.post(
        f"/api/v1/quizzes/{quiz_id}/attempt",
        headers=auth_headers(student_user),
        json={"answers": {valid_qid: "2 ATP"}},
    )
    assert dup_sub.status_code == 409
    assert any(w in dup_sub.json()["detail"].lower() for w in ("already received", "already submitted"))
