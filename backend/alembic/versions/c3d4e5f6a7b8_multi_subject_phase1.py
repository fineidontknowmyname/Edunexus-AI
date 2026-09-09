"""multi_subject_phase1

Adds educator-created categories/subjects, the per-subject Topic Graph storage on
prerequisite_map, chunk-level class_id/subject_id/topic, and the ingestion_jobs queue.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'categories',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'subjects',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('category_id', sa.UUID(), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('category_id', 'name', name='uq_subjects_category_name'),
    )

    op.create_table(
        'ingestion_jobs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('queued', 'processing', 'done', 'failed', name='ingestionjobstatus'),
            nullable=False,
        ),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('claimed_at', sa.DateTime(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('chunk_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ingestion_jobs_status'), 'ingestion_jobs', ['status'], unique=False)

    op.add_column('classes', sa.Column('subject_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_classes_subject_id', 'classes', 'subjects', ['subject_id'], ['id'])

    op.add_column('documents', sa.Column('subject_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_documents_subject_id', 'documents', 'subjects', ['subject_id'], ['id'])

    op.add_column('chunks', sa.Column('subject_id', sa.UUID(), nullable=True))
    op.add_column('chunks', sa.Column('topic', sa.String(length=500), nullable=True))
    op.add_column('chunks', sa.Column('class_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_chunks_subject_id', 'chunks', 'subjects', ['subject_id'], ['id'])
    op.create_foreign_key('fk_chunks_class_id', 'chunks', 'classes', ['class_id'], ['id'])

    op.alter_column('prerequisite_map', 'subject', existing_type=sa.String(length=255), nullable=True)
    op.add_column('prerequisite_map', sa.Column('subject_id', sa.UUID(), nullable=True))
    op.add_column('prerequisite_map', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('prerequisite_map', sa.Column('related_concepts', postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column('prerequisite_map', sa.Column('created_by', sa.UUID(), nullable=True))
    op.add_column('prerequisite_map', sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False))
    op.add_column('prerequisite_map', sa.Column('updated_at', sa.DateTime(), nullable=True))
    op.create_foreign_key('fk_prerequisite_map_subject_id', 'prerequisite_map', 'subjects', ['subject_id'], ['id'])
    op.create_foreign_key('fk_prerequisite_map_created_by', 'prerequisite_map', 'users', ['created_by'], ['id'])
    op.create_unique_constraint(
        'uq_prerequisite_map_subject_topic', 'prerequisite_map', ['subject_id', 'topic']
    )


def downgrade() -> None:
    op.drop_constraint('uq_prerequisite_map_subject_topic', 'prerequisite_map', type_='unique')
    op.drop_constraint('fk_prerequisite_map_created_by', 'prerequisite_map', type_='foreignkey')
    op.drop_constraint('fk_prerequisite_map_subject_id', 'prerequisite_map', type_='foreignkey')
    op.drop_column('prerequisite_map', 'updated_at')
    op.drop_column('prerequisite_map', 'created_at')
    op.drop_column('prerequisite_map', 'created_by')
    op.drop_column('prerequisite_map', 'related_concepts')
    op.drop_column('prerequisite_map', 'description')
    op.drop_column('prerequisite_map', 'subject_id')

    op.drop_constraint('fk_chunks_class_id', 'chunks', type_='foreignkey')
    op.drop_constraint('fk_chunks_subject_id', 'chunks', type_='foreignkey')
    op.drop_column('chunks', 'class_id')
    op.drop_column('chunks', 'topic')
    op.drop_column('chunks', 'subject_id')

    op.drop_constraint('fk_documents_subject_id', 'documents', type_='foreignkey')
    op.drop_column('documents', 'subject_id')

    op.drop_constraint('fk_classes_subject_id', 'classes', type_='foreignkey')
    op.drop_column('classes', 'subject_id')

    op.drop_index(op.f('ix_ingestion_jobs_status'), table_name='ingestion_jobs')
    op.drop_table('ingestion_jobs')
    op.execute('DROP TYPE IF EXISTS ingestionjobstatus')
    op.drop_table('subjects')
    op.drop_table('categories')
