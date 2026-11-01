import uuid
import pytest
from datetime import datetime

from backend.core.database import SessionLocal
from backend.models.db import (
    BloomLevel,
    Class,
    CoverageStatus,
    Document,
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


def test_schema_models_and_curriculum_hierarchy():
    """Verify Phase 1 models, relationships, and constraints in the database."""
    db = SessionLocal()
    created_ids = {}
    try:
        # 1. Fetch an existing subject or create test subject
        subject = db.query(Subject).first()
        assert subject is not None, "Subject must exist in database"

        educator = db.query(User).filter(User.role == UserRole.educator).first()
        assert educator is not None, "Educator must exist in database"

        class_row = db.query(Class).filter(Class.educator_id == educator.id).first()
        assert class_row is not None, "Class must exist in database"

        # 2. Create a test canonical topic in PrerequisiteMap
        test_topic_name = f"Test Topic {uuid.uuid4().hex[:8]}"
        topic_node = PrerequisiteMap(
            subject_id=subject.id,
            subject=subject.name,
            topic=test_topic_name,
            description="Topic for testing Phase 1 schema",
            unit=1,
            order_index=1,
            is_canonical=True,
            created_by=educator.id,
        )
        db.add(topic_node)
        db.flush()
        created_ids["topic_id"] = topic_node.id

        # Verify default / explicit values
        assert topic_node.unit == 1
        assert topic_node.order_index == 1
        assert topic_node.is_canonical is True

        # 3. Create SyllabusSubtopic
        subtopic = SyllabusSubtopic(
            topic_id=topic_node.id,
            name="Test Subtopic A",
            description="Subtopic explanation",
            order_index=1,
        )
        db.add(subtopic)
        db.flush()
        created_ids["subtopic_id"] = subtopic.id

        assert subtopic.name == "Test Subtopic A"
        assert subtopic.topic.id == topic_node.id

        # 4. Create LearningObjective
        objective = LearningObjective(
            topic_id=topic_node.id,
            subtopic_id=subtopic.id,
            code="LO-TEST-101",
            statement="Understand preemptive scheduling principles",
            bloom_level=BloomLevel.understand.value,
            order_index=1,
        )
        db.add(objective)
        db.flush()
        created_ids["objective_id"] = objective.id

        assert objective.statement == "Understand preemptive scheduling principles"
        assert objective.subtopic.id == subtopic.id

        # 5. Create Quiz with Phase 1 metadata
        quiz = Quiz(
            title="Phase 1 Verification Quiz",
            description="A comprehensive quiz testing Phase 1 attributes.",
            unit=1,
            chapter=1,
            class_id=class_row.id,
            created_by_id=educator.id,
            status=ReviewStatus.draft,
            version=1,
            time_limit_minutes=25,
            passing_percentage=65.0,
        )
        db.add(quiz)
        db.flush()
        created_ids["quiz_id"] = quiz.id

        assert quiz.version == 1
        assert quiz.status == ReviewStatus.draft
        assert quiz.time_limit_minutes == 25
        assert quiz.passing_percentage == 65.0

        # 6. Create Questions with new question types and points
        q1 = QuizQuestion(
            quiz_id=quiz.id,
            question_type=QuestionType.single_choice.value,
            question_order=1,
            question_text="What is SJF scheduling?",
            options='["Shortest Job First", "Single Job Fast", "System Job First", "None"]',
            correct_answer="Shortest Job First",
            explanation="SJF prioritizes processes with shortest burst time.",
            points=2.0,
            topic=test_topic_name,
            topic_id=topic_node.id,
            source_page_number=14,
            partial_credit_allowed=False,
            difficulty=QuestionDifficulty.medium,
            status=ReviewStatus.approved,
            version=1,
        )
        q2 = QuizQuestion(
            quiz_id=quiz.id,
            question_type=QuestionType.true_false.value,
            question_order=2,
            question_text="Round Robin scheduling requires a time quantum.",
            options='["True", "False"]',
            correct_answer="True",
            explanation="Time quantum is mandatory in Round Robin.",
            points=1.0,
            topic=test_topic_name,
            topic_id=topic_node.id,
            source_page_number=18,
            difficulty=QuestionDifficulty.easy,
            status=ReviewStatus.approved,
            version=1,
        )
        db.add_all([q1, q2])
        db.flush()
        created_ids["q1_id"] = q1.id
        created_ids["q2_id"] = q2.id

        assert q1.question_type == "single_choice"
        assert q1.points == 2.0
        assert q1.canonical_topic.id == topic_node.id
        assert q2.question_type == "true_false"

        # 7. Create QuestionCurriculumMapping
        mapping = QuestionCurriculumMapping(
            question_id=q1.id,
            topic_id=topic_node.id,
            subtopic_id=subtopic.id,
            objective_id=objective.id,
            bloom_level=BloomLevel.understand.value,
            weight=1.0,
        )
        db.add(mapping)
        db.flush()
        created_ids["mapping_id"] = mapping.id

        assert mapping.learning_objective.statement == objective.statement

        # 8. Create QuizCoverageReport
        report = QuizCoverageReport(
            quiz_id=quiz.id,
            total_topics=5,
            covered_topics=3,
            partially_covered_topics=1,
            missing_topics=1,
            coverage_score=60.0,
            coverage_matrix='{"topics": [{"name": "Test Topic", "status": "covered"}]}',
            warnings='["Uncovered topic: Concurrency"]',
            faculty_acknowledged=True,
            faculty_notes="Advisory acknowledgement test.",
        )
        db.add(report)
        db.flush()
        created_ids["report_id"] = report.id

        assert report.coverage_score == 60.0
        assert report.faculty_acknowledged is True
        assert len(quiz.coverage_reports) == 1

        db.commit()

    finally:
        # Cleanup test records in reverse order
        if "report_id" in created_ids:
            r = db.get(QuizCoverageReport, created_ids["report_id"])
            if r:
                db.delete(r)
        if "mapping_id" in created_ids:
            m = db.get(QuestionCurriculumMapping, created_ids["mapping_id"])
            if m:
                db.delete(m)
        if "quiz_id" in created_ids:
            q = db.get(Quiz, created_ids["quiz_id"])
            if q:
                db.delete(q)
        if "objective_id" in created_ids:
            o = db.get(LearningObjective, created_ids["objective_id"])
            if o:
                db.delete(o)
        if "subtopic_id" in created_ids:
            s = db.get(SyllabusSubtopic, created_ids["subtopic_id"])
            if s:
                db.delete(s)
        if "topic_id" in created_ids:
            t = db.get(PrerequisiteMap, created_ids["topic_id"])
            if t:
                db.delete(t)
        db.commit()
        db.close()


def test_existing_quizzes_and_attempts_unaltered():
    """Verify that all historical quiz, question, and attempt records remain intact and readable."""
    db = SessionLocal()
    try:
        quizzes = db.query(Quiz).all()
        assert len(quizzes) >= 8, f"Expected at least 8 quizzes, found {len(quizzes)}"

        questions = db.query(QuizQuestion).all()
        assert len(questions) >= 48, f"Expected at least 48 questions, found {len(questions)}"

        attempts = db.query(QuizAttempt).all()
        assert len(attempts) >= 15, f"Expected at least 15 attempts, found {len(attempts)}"

        answers = db.query(QuizAttemptAnswer).all()
        assert len(answers) >= 138, f"Expected at least 138 answers, found {len(answers)}"

        # Verify historical attempt retains its score and links to quiz
        sample_attempt = attempts[0]
        assert sample_attempt.quiz is not None
        assert sample_attempt.student is not None
        assert sample_attempt.quiz_version == 1

        # Verify historical question defaults
        sample_q = questions[0]
        assert sample_q.question_type == "single_choice"
        assert sample_q.points == 1.0
        assert sample_q.version == 1

    finally:
        db.close()
