"""phase2_chat

Graph RAG scoping (subject_id on chat_sessions / response_cache), the Socratic
turn-state column, the learning-tag on the response cache, and the topic_behavior
table that feeds Rule 9.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE sessionmode ADD VALUE IF NOT EXISTS 'socratic'")

    op.add_column('chat_sessions', sa.Column('subject_id', sa.UUID(), nullable=True))
    op.add_column('chat_sessions', sa.Column('socratic_state', sa.Text(), nullable=True))
    op.create_foreign_key('fk_chat_sessions_subject_id', 'chat_sessions', 'subjects', ['subject_id'], ['id'])

    op.add_column('response_cache', sa.Column('subject_id', sa.UUID(), nullable=True))
    op.add_column('response_cache', sa.Column('learning_tag', sa.String(length=50), nullable=True))
    op.create_foreign_key('fk_response_cache_subject_id', 'response_cache', 'subjects', ['subject_id'], ['id'])

    op.create_table(
        'topic_behavior',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('topic', sa.String(length=500), nullable=False),
        sa.Column('message_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('follow_up_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('qt_conceptual', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('qt_example', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('qt_direct', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('learning_tag', sa.String(length=50), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('student_id', sa.UUID(), nullable=False),
        sa.Column('subject_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['student_id'], ['users.id']),
        sa.ForeignKeyConstraint(['subject_id'], ['subjects.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('student_id', 'subject_id', 'topic', name='uq_topic_behavior_student_subject_topic'),
    )


def downgrade() -> None:
    op.drop_table('topic_behavior')

    op.drop_constraint('fk_response_cache_subject_id', 'response_cache', type_='foreignkey')
    op.drop_column('response_cache', 'learning_tag')
    op.drop_column('response_cache', 'subject_id')

    op.drop_constraint('fk_chat_sessions_subject_id', 'chat_sessions', type_='foreignkey')
    op.drop_column('chat_sessions', 'socratic_state')
    op.drop_column('chat_sessions', 'subject_id')
    # note: the 'socratic' enum value is left in place (Postgres cannot drop enum values)
