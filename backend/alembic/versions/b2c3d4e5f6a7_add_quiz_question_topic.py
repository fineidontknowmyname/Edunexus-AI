"""add_quiz_question_topic"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('quiz_questions', sa.Column('topic', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('quiz_questions', 'topic')
