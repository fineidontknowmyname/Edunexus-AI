"""phase11_topic_mastery_v2

Revision ID: phase11_topic_mastery_v2
Revises: phase10_quiz_attempt_answers
Create Date: 2026-10-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "phase11_topic_mastery_v2"
down_revision: Union[str, None] = "phase10_quiz_attempt_answers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("topic_mastery", sa.Column("mastery_v2", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("topic_mastery", "mastery_v2")
