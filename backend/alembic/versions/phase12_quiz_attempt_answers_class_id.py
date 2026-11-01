"""phase12_answers_class_id

Revision ID: phase12_answers_class_id
Revises: phase11_topic_mastery_v2
Create Date: 2026-10-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "phase12_answers_class_id"
down_revision: Union[str, None] = "phase11_topic_mastery_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quiz_attempt_answers",
        sa.Column(
            "class_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("classes.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_quiz_attempt_answers_class_id",
        "quiz_attempt_answers",
        ["class_id"],
        unique=False,
    )
    op.create_index(
        "ix_quiz_attempt_answers_student_class_topic_answered",
        "quiz_attempt_answers",
        ["student_id", "class_id", "topic_key", "answered_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_quiz_attempt_answers_student_class_topic_answered",
        table_name="quiz_attempt_answers",
    )
    op.drop_index("ix_quiz_attempt_answers_class_id", table_name="quiz_attempt_answers")
    op.drop_column("quiz_attempt_answers", "class_id")
