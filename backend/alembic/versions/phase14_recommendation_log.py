"""phase14_recommendation_log

Revision ID: phase14_recommendation_log
Revises: phase13_learning_resources
Create Date: 2026-10-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "phase14_recommendation_log"
down_revision: Union[str, None] = "phase13_learning_resources"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recommendation_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("topic", sa.String(length=500), nullable=False),
        sa.Column("mode", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("outcome_score_before", sa.Float(), nullable=True),
        sa.Column("outcome_score_after", sa.Float(), nullable=True),
        sa.Column("outcome_delta", sa.Float(), nullable=True),
        sa.Column(
            "student_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "class_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("classes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "outcome_attempt_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("quiz_attempts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_recommendation_logs_student_id", "recommendation_logs", ["student_id"])
    op.create_index("ix_recommendation_logs_class_id", "recommendation_logs", ["class_id"])
    op.create_index("ix_recommendation_logs_topic", "recommendation_logs", ["topic"])


def downgrade() -> None:
    op.drop_index("ix_recommendation_logs_topic", table_name="recommendation_logs")
    op.drop_index("ix_recommendation_logs_class_id", table_name="recommendation_logs")
    op.drop_index("ix_recommendation_logs_student_id", table_name="recommendation_logs")
    op.drop_table("recommendation_logs")
