"""Phase 20: Add generation_meta to quiz_questions

Revision ID: phase20_quiz_question_generation_meta
Revises: phase19_quiz_remediation_constraints
Create Date: 2026-10-31 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "phase20_quiz_question_generation_meta"
down_revision: Union[str, None] = "phase19_quiz_remediation_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quiz_questions",
        sa.Column("generation_meta", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("quiz_questions", "generation_meta")
