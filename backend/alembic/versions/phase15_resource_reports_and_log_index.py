"""phase15_reports_and_log_index

Revision ID: phase15_reports_and_log_index
Revises: phase14_recommendation_log
Create Date: 2026-10-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "phase15_reports_and_log_index"
down_revision: Union[str, None] = "phase14_recommendation_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. resource_reports table for F1
    op.create_table(
        "resource_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "resource_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learning_resources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "student_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.UniqueConstraint("resource_id", "student_id", name="uq_resource_reports_resource_student"),
    )
    op.create_index("ix_resource_reports_resource_id", "resource_reports", ["resource_id"])
    op.create_index("ix_resource_reports_student_id", "resource_reports", ["student_id"])

    # 2. composite index on recommendation_logs for F3
    op.create_index(
        "ix_recommendation_logs_student_class_topic_created",
        "recommendation_logs",
        ["student_id", "class_id", "topic", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_recommendation_logs_student_class_topic_created", table_name="recommendation_logs")
    op.drop_index("ix_resource_reports_student_id", table_name="resource_reports")
    op.drop_index("ix_resource_reports_resource_id", table_name="resource_reports")
    op.drop_table("resource_reports")
