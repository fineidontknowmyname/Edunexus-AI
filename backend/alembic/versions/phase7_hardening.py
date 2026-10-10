"""phase7_hardening"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'phase7_hardening'
down_revision: Union[str, None] = 'phase6_refresh_tokens'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LOOKUP_INDEXES = [
    ('ix_chat_messages_session_created', 'chat_messages', ['session_id', 'created_at']),
    ('ix_chat_sessions_student_created', 'chat_sessions', ['student_id', 'created_at']),
    ('ix_class_enrollments_class_id', 'class_enrollments', ['class_id']),
    ('ix_class_enrollments_student_id', 'class_enrollments', ['student_id']),
    ('ix_topic_mastery_student_class', 'topic_mastery', ['student_id', 'class_id']),
    ('ix_misconceptions_student_class', 'misconceptions', ['student_id', 'class_id']),
    ('ix_quiz_attempts_student_quiz', 'quiz_attempts', ['student_id', 'quiz_id']),
    ('ix_quizzes_class_id', 'quizzes', ['class_id']),
    ('ix_quiz_questions_quiz_id', 'quiz_questions', ['quiz_id']),
    ('ix_documents_class_id', 'documents', ['class_id']),
    ('ix_chunks_document_id', 'chunks', ['document_id']),
    ('ix_chunks_subject_topic', 'chunks', ['subject_id', 'topic']),
    ('ix_interaction_patterns_student_id', 'interaction_patterns', ['student_id']),
    ('ix_educator_notes_student_class', 'educator_notes', ['student_id', 'class_id']),
    ('ix_classes_educator_id', 'classes', ['educator_id']),
]


def upgrade() -> None:
    for name, table, columns in LOOKUP_INDEXES:
        op.create_index(name, table, columns, unique=False)

    op.create_table(
        'document_files',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('data', sa.LargeBinary(), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('document_id', name='uq_document_files_document_id'),
    )
    op.alter_column('documents', 'file_path', existing_type=sa.String(length=1000), nullable=True)

    op.add_column('response_cache', sa.Column('class_id', sa.UUID(), nullable=True))
    op.add_column('response_cache', sa.Column('session_mode', sa.String(length=20), nullable=True))
    op.create_foreign_key('fk_response_cache_class_id', 'response_cache', 'classes', ['class_id'], ['id'])
    op.create_index(op.f('ix_response_cache_class_id'), 'response_cache', ['class_id'], unique=False)

    op.add_column('topic_mastery', sa.Column('subject_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_topic_mastery_subject_id', 'topic_mastery', 'subjects', ['subject_id'], ['id'])
    op.create_index(op.f('ix_topic_mastery_subject_id'), 'topic_mastery', ['subject_id'], unique=False)

    op.add_column('misconceptions', sa.Column('subject_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_misconceptions_subject_id', 'misconceptions', 'subjects', ['subject_id'], ['id'])
    op.create_index(op.f('ix_misconceptions_subject_id'), 'misconceptions', ['subject_id'], unique=False)

    op.add_column('interaction_patterns', sa.Column('class_id', sa.UUID(), nullable=True))
    op.add_column('interaction_patterns', sa.Column('subject_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_interaction_patterns_class_id', 'interaction_patterns', 'classes', ['class_id'], ['id'])
    op.create_foreign_key('fk_interaction_patterns_subject_id', 'interaction_patterns', 'subjects', ['subject_id'], ['id'])
    op.create_index(op.f('ix_interaction_patterns_class_id'), 'interaction_patterns', ['class_id'], unique=False)
    op.create_index(op.f('ix_interaction_patterns_subject_id'), 'interaction_patterns', ['subject_id'], unique=False)

    op.execute(
        """
        UPDATE topic_mastery tm SET subject_id = c.subject_id
        FROM classes c WHERE c.id = tm.class_id AND tm.subject_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE misconceptions m SET subject_id = c.subject_id
        FROM classes c WHERE c.id = m.class_id AND m.subject_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE interaction_patterns ip SET class_id = single.class_id, subject_id = c.subject_id
        FROM (
            SELECT student_id, (array_agg(class_id))[1] AS class_id
            FROM class_enrollments GROUP BY student_id HAVING count(*) = 1
        ) single
        JOIN classes c ON c.id = single.class_id
        WHERE ip.student_id = single.student_id AND ip.class_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_interaction_patterns_subject_id'), table_name='interaction_patterns')
    op.drop_index(op.f('ix_interaction_patterns_class_id'), table_name='interaction_patterns')
    op.drop_constraint('fk_interaction_patterns_subject_id', 'interaction_patterns', type_='foreignkey')
    op.drop_constraint('fk_interaction_patterns_class_id', 'interaction_patterns', type_='foreignkey')
    op.drop_column('interaction_patterns', 'subject_id')
    op.drop_column('interaction_patterns', 'class_id')

    op.drop_index(op.f('ix_misconceptions_subject_id'), table_name='misconceptions')
    op.drop_constraint('fk_misconceptions_subject_id', 'misconceptions', type_='foreignkey')
    op.drop_column('misconceptions', 'subject_id')

    op.drop_index(op.f('ix_topic_mastery_subject_id'), table_name='topic_mastery')
    op.drop_constraint('fk_topic_mastery_subject_id', 'topic_mastery', type_='foreignkey')
    op.drop_column('topic_mastery', 'subject_id')

    op.drop_index(op.f('ix_response_cache_class_id'), table_name='response_cache')
    op.drop_constraint('fk_response_cache_class_id', 'response_cache', type_='foreignkey')
    op.drop_column('response_cache', 'session_mode')
    op.drop_column('response_cache', 'class_id')

    op.execute("UPDATE documents SET file_path = '' WHERE file_path IS NULL")
    op.alter_column('documents', 'file_path', existing_type=sa.String(length=1000), nullable=False)
    op.drop_table('document_files')

    for name, table, _columns in reversed(LOOKUP_INDEXES):
        op.drop_index(name, table_name=table)
