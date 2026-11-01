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
from backend.services import quiz_service
from backend.tests.conftest import auth_headers


@pytest.fixture
def clean_database(db: Session, sample_class: Class, educator_user: User, student_user: User):
    def _cleanup():
        db.rollback()
        # Clean quizzes and attempts created in this class
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
def topic_curriculum(clean_database, db: Session, sample_class: Class, educator_user: User, student_user: User):
    """Sets up a comprehensive curriculum environment with 3 distinct chunks."""
    # Enroll student in class
    enrollment = ClassEnrollment(
        class_id=sample_class.id,
        student_id=student_user.id,
    )
    db.add(enrollment)

    # Category setup
    cat = db.query(Category).first()
    if not cat:
        cat = Category(name=f"BioSci-{uuid.uuid4().hex[:4]}", created_by=educator_user.id)
        db.add(cat)
        db.flush()

    # Subject setup
    subject = Subject(
        name=f"Biochemistry {uuid.uuid4().hex[:6]}",
        category_id=cat.id,
        created_by=educator_user.id,
    )
    db.add(subject)
    db.flush()

    sample_class.subject_id = subject.id
    sample_class.subject = subject.name

    # Document
    doc = Document(
        title="Cellular Energetics Principles",
        filename="bio_energetics.pdf",
        status=DocumentStatus.ready,
        is_indexed=True,
        chunk_count=3,
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
        topic="Oxidative Phosphorylation",
        description="ATP synthesis driven by electron transfer along the mitochondrial inner membrane.",
        unit=3,
        order_index=1,
        is_canonical=True,
        source_document_id=doc.id,
        source_page_number=110,
        created_by=educator_user.id,
    )
    db.add(topic)
    db.flush()

    # Chunk 1: Electron Transport Chain
    chunk1 = Chunk(
        document_id=doc.id,
        class_id=sample_class.id,
        subject_id=subject.id,
        subject=subject.name,
        topic="Oxidative Phosphorylation",
        page_number=110,
        chunk_index=0,
        token_count=140,
        section_heading="The Electron Transport Chain Complexes",
        text=(
            "Complexes I through IV of the electron transport chain pump protons from the matrix "
            "into the intermembrane space of the mitochondria, establishing a steep electrochemical proton gradient. "
            "Oxygen serves as the terminal electron acceptor, being reduced to water at Complex IV."
        ),
        contextual_prefix="Chapter 3: Respiration",
        full_text=(
            "Chapter 3: Respiration. Complexes I through IV pump protons to create an electrochemical gradient. "
            "Oxygen is the terminal electron acceptor."
        ),
        embedding=[0.08] * 384,
    )

    # Chunk 2: ATP Synthase Mechanism
    chunk2 = Chunk(
        document_id=doc.id,
        class_id=sample_class.id,
        subject_id=subject.id,
        subject=subject.name,
        topic="Oxidative Phosphorylation",
        page_number=112,
        chunk_index=1,
        token_count=135,
        section_heading="Chemiosmotic ATP Synthesis",
        text=(
            "ATP synthase utilizes the proton motive force to catalyze the phosphorylation of ADP to ATP. "
            "The flow of protons through the F0 subunit drives rotation of the gamma subunit in F1, "
            "inducing conformational changes that synthesize ATP."
        ),
        contextual_prefix="Chapter 3: Respiration",
        full_text="ATP synthase uses the proton motive force to synthesize ATP from ADP and inorganic phosphate.",
        embedding=[0.07] * 384,
    )

    # Chunk 3: Chemical Uncouplers and Inhibitors
    chunk3 = Chunk(
        document_id=doc.id,
        class_id=sample_class.id,
        subject_id=subject.id,
        subject=subject.name,
        topic="Oxidative Phosphorylation",
        page_number=115,
        chunk_index=2,
        token_count=125,
        section_heading="Uncoupling and Inhibitors",
        text=(
            "Chemical uncouplers such as 2,4-dinitrophenol (DNP) dissipate the proton gradient across the inner "
            "mitochondrial membrane without inhibiting the electron transport chain, releasing energy as heat instead of ATP."
        ),
        contextual_prefix="Chapter 3: Respiration",
        full_text="DNP uncouples electron transport from phosphorylation, dissipating the proton motive force as heat.",
        embedding=[0.06] * 384,
    )

    db.add_all([chunk1, chunk2, chunk3])
    db.commit()

    return {
        "subject": subject,
        "doc": doc,
        "topic": topic,
        "chunk1": chunk1,
        "chunk2": chunk2,
        "chunk3": chunk3,
    }


# ==============================================================================
# Unit Tests for Duplicate Detection & Grounding Guards
# ==============================================================================

def test_near_duplicate_detection_jaccard():
    """Validates that Jaccard similarity correctly detects paraphrased duplicate questions."""
    q1 = {
        "question_text": "What acts as the terminal electron acceptor in the electron transport chain?",
        "options": ["Oxygen", "Carbon Dioxide", "Water", "NAD+"],
        "correct_answer": "Oxygen",
    }
    # Highly similar paraphrased candidate
    q2_dup = {
        "question_text": "In the electron transport chain, which molecule acts as the terminal electron acceptor?",
        "options": ["Oxygen", "Glucose", "Pyruvate", "Lactate"],
        "correct_answer": "Oxygen",
    }
    # Completely distinct question
    q3_distinct = {
        "question_text": "How does 2,4-dinitrophenol affect ATP production in mitochondria?",
        "options": ["Inhibits Complex I", "Dissipates proton gradient", "Blocks ATP synthase", "Destroys ribosomes"],
        "correct_answer": "Dissipates proton gradient",
    }

    is_dup1, reason1 = quiz_service.is_near_duplicate_question(q2_dup, [q1])
    assert is_dup1 is True
    assert "similarity" in reason1.lower()

    is_dup2, reason2 = quiz_service.is_near_duplicate_question(q3_distinct, [q1])
    assert is_dup2 is False
    assert reason2 == "Unique"


def test_near_duplicate_detection_option_collision():
    """Validates that option set collision triggers duplicate rejection even if question is rephrased."""
    q1 = {
        "question_text": "Identify the primary proton pumping complexes.",
        "options": ["Complex I", "Complex III", "Complex IV", "Complex II"],
        "correct_answer": "Complex I",
    }
    q2_collision = {
        "question_text": "Which complex is located in the inner mitochondrial membrane?",
        "options": ["Complex I", "Complex III", "Complex IV", "Complex II"],
        "correct_answer": "Complex I",
    }

    is_dup, reason = quiz_service.is_near_duplicate_question(q2_collision, [q1])
    assert is_dup is True
    assert "colliding answer options" in reason.lower()


def test_chunk_grounding_validation(topic_curriculum):
    """Validates that hallucinated questions or unsupported answers are rejected by grounding validation."""
    chunk1 = topic_curriculum["chunk1"]

    # Legitimate grounded question
    grounded_q = {
        "question_text": "Which molecule serves as the terminal electron acceptor at Complex IV?",
        "options": ["Oxygen", "Water", "NADH", "Cytochrome c"],
        "correct_answer": "Oxygen",
        "question_type": "single_choice",
        "explanation": "Oxygen serves as the terminal electron acceptor at Complex IV.",
    }
    valid, reason = quiz_service.validate_chunk_grounding(grounded_q, chunk1, "Oxidative Phosphorylation")
    assert valid is True
    assert reason == "Valid"

    # Hallucinated answer not supported in chunk text
    hallucinated_q = {
        "question_text": "Which vitamin derivative acts as the cofactor for succinate dehydrogenase?",
        "options": ["Riboflavin", "Cobalamin", "Biotin", "Thiamine"],
        "correct_answer": "Riboflavin",
        "question_type": "single_choice",
        "explanation": "Riboflavin is a B vitamin derivative.",
    }
    valid_h, reason_h = quiz_service.validate_chunk_grounding(hallucinated_q, chunk1, "Oxidative Phosphorylation")
    assert valid_h is False
    assert "not supported" in reason_h.lower() or "insufficient factual overlap" in reason_h.lower()

    # Irrelevant topic question
    irrelevant_q = {
        "question_text": "What is the capital city of France during the medieval era?",
        "options": ["Paris", "Lyon", "Marseille", "Nice"],
        "correct_answer": "Paris",
        "question_type": "single_choice",
        "explanation": "Paris is the capital.",
    }
    valid_irr, reason_irr = quiz_service.validate_chunk_grounding(irrelevant_q, chunk1, "Oxidative Phosphorylation")
    assert valid_irr is False
    assert "no lexical connection" in reason_irr.lower() or "insufficient factual overlap" in reason_irr.lower()


# ==============================================================================
# Integration Test for Phase 3 End-to-End Generation Quality & Provenance
# ==============================================================================

def test_topic_quiz_generation_quality_pipeline(client, db: Session, sample_class: Class, student_user: User, topic_curriculum):
    """Tests the full generation pipeline under Phase 3 requirements:
    1. Rejects ungrounded candidates and duplicates.
    2. Persists cognitive taxonomy levels (remember, understand, apply) in QuestionCurriculumMapping.
    3. Persists structured audit metadata in Quiz.description.
    4. Accurately attributes distinct source chunks and page numbers.
    """
    topic = topic_curriculum["topic"]

    # LLM returns 5 candidates:
    # Item 1: Valid "remember" question grounded in Chunk 1
    # Item 2: Duplicate of Item 1 (should be filtered out)
    # Item 3: Hallucinated / ungrounded question (should be filtered out)
    # Item 4: Valid "understand" question grounded in Chunk 2
    # Item 5: Valid "apply" question grounded in Chunk 3
    mock_candidates = [
        {
            "question": "What serves as the terminal electron acceptor in the electron transport chain?",
            "question_type": "single_choice",
            "options": ["Oxygen", "Carbon Dioxide", "Water", "Glucose"],
            "correct_answer": "Oxygen",
            "difficulty": "easy",
            "bloom_level": "remember",
            "explanation": "Oxygen is reduced to water at Complex IV as the terminal electron acceptor.",
            "chunk_index": 1,
        },
        {
            # Duplicate of Item 1
            "question": "What molecule acts as the terminal electron acceptor in the electron transport chain?",
            "options": ["Oxygen", "Carbon Dioxide", "Water", "Glucose"],
            "correct_answer": "Oxygen",
            "difficulty": "easy",
            "bloom_level": "remember",
            "explanation": "Oxygen is the terminal electron acceptor.",
            "chunk_index": 1,
        },
        {
            # Hallucinated question with no grounding in any chunk
            "question": "Which Roman emperor sponsored the first public biological anatomical theater?",
            "question_type": "single_choice",
            "options": ["Augustus", "Nero", "Trajan", "Marcus Aurelius"],
            "correct_answer": "Augustus",
            "difficulty": "hard",
            "bloom_level": "remember",
            "explanation": "Augustus was an emperor.",
            "chunk_index": 1,
        },
        {
            # Valid question grounded in Chunk 2
            "question": "How does the flow of protons through the F0 subunit drive ATP synthesis?",
            "question_type": "single_choice",
            "options": [
                "Drives rotation of the gamma subunit in F1",
                "Directly hydrolyzes ATP to ADP",
                "Transports pyruvate into the matrix",
                "Blocks electron flow at Complex IV",
            ],
            "correct_answer": "Drives rotation of the gamma subunit in F1",
            "difficulty": "medium",
            "bloom_level": "understand",
            "explanation": "Proton flow through F0 drives rotation of the gamma subunit in F1, inducing ATP synthesis.",
            "chunk_index": 2,
        },
        {
            # Valid question grounded in Chunk 3
            "question": "If 2,4-dinitrophenol (DNP) is added to mitochondria, what is the expected metabolic consequence?",
            "question_type": "single_choice",
            "options": [
                "Proton gradient dissipates and energy is released as heat instead of ATP",
                "Complex I electron transport is completely arrested",
                "Oxygen consumption drops to zero immediately",
                "ATP synthesis rate increases twofold",
            ],
            "correct_answer": "Proton gradient dissipates and energy is released as heat instead of ATP",
            "difficulty": "hard",
            "bloom_level": "apply",
            "explanation": "Chemical uncouplers like DNP dissipate the proton gradient, releasing energy as heat without ATP.",
            "chunk_index": 3,
        },
    ]

    with patch("backend.services.rag_service.get_llm_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.generate.return_value = json.dumps(mock_candidates)
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
    quiz_data = response.json()
    quiz_id = quiz_data["quiz_id"]
    assert quiz_data["question_count"] == 3

    # Inspect persisted Quiz
    quiz_row = db.get(Quiz, uuid.UUID(quiz_id))
    assert quiz_row is not None
    assert quiz_row.generation_type == "topic_practice"

    # Inspect structured audit metadata in Quiz.description
    metadata = json.loads(quiz_row.description)
    assert metadata["type"] == "topic_practice"
    assert metadata["canonical_topic"] == "Oxidative Phosphorylation"
    assert metadata["candidates_evaluated"] == 5
    assert metadata["accepted_count"] == 3
    assert metadata["rejected_count"] == 2
    assert len(metadata["rejection_sample"]) == 2

    rejection_reasons = [r["reason"].lower() for r in metadata["rejection_sample"]]
    assert any("duplicate" in r for r in rejection_reasons)
    assert any("grounding" in r for r in rejection_reasons)

    # Inspect QuizQuestions
    assert len(quiz_row.questions) == 3
    questions = sorted(quiz_row.questions, key=lambda q: q.question_order)

    # Verify provenance attribution across distinct chunks and page numbers
    distinct_chunks = {q.source_chunk_id for q in questions}
    assert len(distinct_chunks) == 3
    distinct_pages = {q.source_page_number for q in questions}
    assert distinct_pages == {110, 112, 115}

    # Inspect QuestionCurriculumMapping and Bloom level persistence
    mappings = (
        db.query(QuestionCurriculumMapping)
        .filter(QuestionCurriculumMapping.question_id.in_([q.id for q in questions]))
        .all()
    )
    assert len(mappings) == 3
    bloom_levels = {m.bloom_level for m in mappings}
    assert bloom_levels == {"remember", "understand", "apply"}
    for m in mappings:
        assert m.topic_id == topic.id
        assert m.weight == 1.0
