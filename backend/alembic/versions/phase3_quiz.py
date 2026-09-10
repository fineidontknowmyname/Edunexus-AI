"""phase3_quiz"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'phase3_quiz'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('topic_mastery', sa.Column('last_quiz_passed', sa.Boolean(), nullable=True))

    op.create_table(
        'misconception_rules',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('topic', sa.String(length=500), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('wrong_answer_keywords', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('question_keywords', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('subject_id', sa.UUID(), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['subject_id'], ['subjects.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_misconception_rules_subject_id'), 'misconception_rules', ['subject_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_misconception_rules_subject_id'), table_name='misconception_rules')
    op.drop_table('misconception_rules')
    op.drop_column('topic_mastery', 'last_quiz_passed')
