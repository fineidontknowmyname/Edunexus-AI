"""phase16_quiz_foundation

Revision ID: phase16_quiz_foundation
Revises: phase15_reports_and_log_index
Create Date: 2026-10-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "phase16_quiz_foundation"
down_revision: Union[str, None] = "phase15_reports_and_log_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Safely add 'draft' and 'archived' values to reviewstatus enum in PostgreSQL
    op.execute("ALTER TYPE reviewstatus ADD VALUE IF NOT EXISTS 'draft'")
    op.execute("ALTER TYPE reviewstatus ADD VALUE IF NOT EXISTS 'archived'")

    # 2. Additive columns on prerequisite_map (canonical curriculum topics)
    op.add_column("prerequisite_map", sa.Column("unit", sa.Integer(), nullable=True))
    op.add_column(
        "prerequisite_map",
        sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "prerequisite_map",
        sa.Column("is_canonical", sa.Boolean(), server_default="true", nullable=False),
    )

    # 3. Create syllabus_subtopics table
    op.create_table(
        "syllabus_subtopics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prerequisite_map.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("topic_id", "name", name="uq_subtopics_topic_name"),
    )
    op.create_index("ix_syllabus_subtopics_topic_id", "syllabus_subtopics", ["topic_id"])

    # 4. Create learning_objectives table
    op.create_table(
        "learning_objectives",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prerequisite_map.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subtopic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("syllabus_subtopics.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("code", sa.String(50), nullable=True),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("bloom_level", sa.String(50), nullable=True),
        sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_learning_objectives_topic_id", "learning_objectives", ["topic_id"])
    op.create_index("ix_learning_objectives_subtopic_id", "learning_objectives", ["subtopic_id"])

    # 5. Additive columns on quizzes
    op.add_column("quizzes", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "quizzes",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column("quizzes", sa.Column("time_limit_minutes", sa.Integer(), nullable=True))
    op.add_column(
        "quizzes",
        sa.Column("passing_percentage", sa.Float(), server_default="60.0", nullable=False),
    )
    op.add_column(
        "quizzes",
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # 6. Additive columns on quiz_questions
    op.add_column(
        "quiz_questions",
        sa.Column("question_type", sa.String(50), server_default="single_choice", nullable=False),
    )
    op.add_column(
        "quiz_questions",
        sa.Column("question_order", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column("quiz_questions", sa.Column("explanation", sa.Text(), nullable=True))
    op.add_column(
        "quiz_questions",
        sa.Column("points", sa.Float(), server_default="1.0", nullable=False),
    )
    op.add_column("quiz_questions", sa.Column("source_page_number", sa.Integer(), nullable=True))
    op.add_column(
        "quiz_questions",
        sa.Column("partial_credit_allowed", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "quiz_questions",
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prerequisite_map.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "quiz_questions",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "quiz_questions",
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_quiz_questions_topic_id", "quiz_questions", ["topic_id"])

    # 7. Create question_curriculum_mappings table
    op.create_table(
        "question_curriculum_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("quiz_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prerequisite_map.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subtopic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("syllabus_subtopics.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "objective_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learning_objectives.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("bloom_level", sa.String(50), nullable=True),
        sa.Column("weight", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_qcm_question_id", "question_curriculum_mappings", ["question_id"])
    op.create_index("ix_qcm_topic_id", "question_curriculum_mappings", ["topic_id"])
    op.create_index("ix_qcm_objective_id", "question_curriculum_mappings", ["objective_id"])

    # 8. Create quiz_coverage_reports table
    op.create_table(
        "quiz_coverage_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "quiz_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("quizzes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("total_topics", sa.Integer(), server_default="0", nullable=False),
        sa.Column("covered_topics", sa.Integer(), server_default="0", nullable=False),
        sa.Column("partially_covered_topics", sa.Integer(), server_default="0", nullable=False),
        sa.Column("missing_topics", sa.Integer(), server_default="0", nullable=False),
        sa.Column("coverage_score", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("coverage_matrix", sa.Text(), nullable=True),
        sa.Column("warnings", sa.Text(), nullable=True),
        sa.Column("faculty_acknowledged", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("faculty_notes", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_quiz_coverage_reports_quiz_id", "quiz_coverage_reports", ["quiz_id"])

    # 9. Additive columns on quiz_attempts
    op.add_column(
        "quiz_attempts",
        sa.Column("quiz_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column("quiz_attempts", sa.Column("points_earned", sa.Float(), nullable=True))
    op.add_column("quiz_attempts", sa.Column("max_points", sa.Float(), nullable=True))

    # 10. Additive columns on quiz_attempt_answers
    op.add_column("quiz_attempt_answers", sa.Column("points_awarded", sa.Float(), nullable=True))
    op.add_column("quiz_attempt_answers", sa.Column("max_points", sa.Float(), nullable=True))
    op.add_column("quiz_attempt_answers", sa.Column("selected_options", sa.Text(), nullable=True))

    # 11. Additive columns on documents
    op.add_column("documents", sa.Column("file_hash_sha256", sa.String(64), nullable=True))
    op.add_column("documents", sa.Column("mime_type", sa.String(100), nullable=True))
    op.add_column("documents", sa.Column("file_size_bytes", sa.Integer(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "documents",
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_documents_file_hash_sha256", "documents", ["file_hash_sha256"])


def downgrade() -> None:
    # 11. Documents
    op.drop_index("ix_documents_file_hash_sha256", table_name="documents")
    op.drop_column("documents", "updated_at")
    op.drop_column("documents", "version")
    op.drop_column("documents", "file_size_bytes")
    op.drop_column("documents", "mime_type")
    op.drop_column("documents", "file_hash_sha256")

    # 10. Quiz attempt answers
    op.drop_column("quiz_attempt_answers", "selected_options")
    op.drop_column("quiz_attempt_answers", "max_points")
    op.drop_column("quiz_attempt_answers", "points_awarded")

    # 9. Quiz attempts
    op.drop_column("quiz_attempts", "max_points")
    op.drop_column("quiz_attempts", "points_earned")
    op.drop_column("quiz_attempts", "quiz_version")

    # 8. Quiz coverage reports
    op.drop_index("ix_quiz_coverage_reports_quiz_id", table_name="quiz_coverage_reports")
    op.drop_table("quiz_coverage_reports")

    # 7. Question curriculum mappings
    op.drop_index("ix_qcm_objective_id", table_name="question_curriculum_mappings")
    op.drop_index("ix_qcm_topic_id", table_name="question_curriculum_mappings")
    op.drop_index("ix_qcm_question_id", table_name="question_curriculum_mappings")
    op.drop_table("question_curriculum_mappings")

    # 6. Quiz questions
    op.drop_index("ix_quiz_questions_topic_id", table_name="quiz_questions")
    op.drop_column("quiz_questions", "updated_at")
    op.drop_column("quiz_questions", "version")
    op.drop_column("quiz_questions", "topic_id")
    op.drop_column("quiz_questions", "partial_credit_allowed")
    op.drop_column("quiz_questions", "source_page_number")
    op.drop_column("quiz_questions", "points")
    op.drop_column("quiz_questions", "explanation")
    op.drop_column("quiz_questions", "question_order")
    op.drop_column("quiz_questions", "question_type")

    # 5. Quizzes
    op.drop_column("quizzes", "updated_at")
    op.drop_column("quizzes", "passing_percentage")
    op.drop_column("quizzes", "time_limit_minutes")
    op.drop_column("quizzes", "version")
    op.drop_column("quizzes", "description")

    # 4. Learning objectives
    op.drop_index("ix_learning_objectives_subtopic_id", table_name="learning_objectives")
    op.drop_index("ix_learning_objectives_topic_id", table_name="learning_objectives")
    op.drop_table("learning_objectives")

    # 3. Syllabus subtopics
    op.drop_index("ix_syllabus_subtopics_topic_id", table_name="syllabus_subtopics")
    op.drop_table("syllabus_subtopics")

    # 2. Prerequisite map
    op.drop_column("prerequisite_map", "is_canonical")
    op.drop_column("prerequisite_map", "order_index")
    op.drop_column("prerequisite_map", "unit")

    # 1. Note: Postgres does not support removing enum values from an existing type with ALTER TYPE.
