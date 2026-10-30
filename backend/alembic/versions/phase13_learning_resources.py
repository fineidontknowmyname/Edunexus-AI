"""phase13_learning_resources

Revision ID: phase13_learning_resources
Revises: phase12_answers_class_id
Create Date: 2026-10-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "phase13_learning_resources"
down_revision: Union[str, None] = "phase12_answers_class_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    resource_type_enum = sa.Enum("youtube", "notes", name="resourcetype")
    review_status_enum = postgresql.ENUM(
        "pending_review", "approved", "rejected", name="reviewstatus", create_type=False
    )

    op.create_table(
        "learning_resources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("topic", sa.String(length=500), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("resource_type", resource_type_enum, nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("status", review_status_enum, nullable=False, server_default="pending_review"),
        sa.Column("helpful_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("report_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column(
            "class_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("classes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
    )
    op.create_index("ix_learning_resources_topic", "learning_resources", ["topic"])
    op.create_index("ix_learning_resources_class_id", "learning_resources", ["class_id"])
    op.create_index("ix_learning_resources_status", "learning_resources", ["status"])

    op.create_table(
        "resource_votes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vote_type", sa.String(length=16), nullable=False, server_default="helpful"),
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
        sa.UniqueConstraint("resource_id", "student_id", name="uq_resource_votes_resource_student"),
    )


def downgrade() -> None:
    op.drop_table("resource_votes")
    op.drop_index("ix_learning_resources_status", table_name="learning_resources")
    op.drop_index("ix_learning_resources_class_id", table_name="learning_resources")
    op.drop_index("ix_learning_resources_topic", table_name="learning_resources")
    op.drop_table("learning_resources")
    sa.Enum("youtube", "notes", name="resourcetype").drop(op.get_bind(), checkfirst=True)
