"""Phase 21: Persist question reports table

Revision ID: phase21_question_reports
Revises: phase20_quiz_question_generation_meta
Create Date: 2026-11-01 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "phase21_question_reports"
down_revision: Union[str, None] = "phase20_quiz_question_generation_meta"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "question_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("quiz_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "quiz_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("quizzes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "class_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("classes.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "reporter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reporter_role", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "question_id",
            "reporter_id",
            "category",
            name="uq_question_reports_question_reporter_category",
        ),
    )
    op.create_index(
        "ix_question_reports_question_id",
        "question_reports",
        ["question_id"],
    )
    op.create_index(
        "ix_question_reports_quiz_id",
        "question_reports",
        ["quiz_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_question_reports_quiz_id", table_name="question_reports")
    op.drop_index("ix_question_reports_question_id", table_name="question_reports")
    op.drop_table("question_reports")
