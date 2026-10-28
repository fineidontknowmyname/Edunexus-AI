"""phase10_quiz_attempt_answers

Revision ID: phase10_quiz_attempt_answers
Revises: phase9_join_codes
Create Date: 2026-10-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "phase10_quiz_attempt_answers"
down_revision: Union[str, None] = "phase9_join_codes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quiz_attempt_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "attempt_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("quiz_attempts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "student_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("quiz_questions.id"),
            nullable=False,
        ),
        sa.Column("topic", sa.String(length=500), nullable=True),
        sa.Column("topic_key", sa.String(length=500), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("difficulty", sa.String(length=16), nullable=True),
        sa.Column("option_count", sa.Integer(), nullable=True),
        sa.Column("answered_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("attempt_id", "question_id", name="uq_quiz_attempt_answers_attempt_question"),
    )
    op.create_index(
        "ix_quiz_attempt_answers_student_topic_key_answered",
        "quiz_attempt_answers",
        ["student_id", "topic_key", "answered_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_quiz_attempt_answers_student_topic_key_answered", table_name="quiz_attempt_answers")
    op.drop_table("quiz_attempt_answers")
