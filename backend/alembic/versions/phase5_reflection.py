"""phase5_reflection"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'phase5_reflection'
down_revision: Union[str, None] = 'phase3_quiz'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'reflections',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('topic', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('student_id', sa.UUID(), nullable=False),
        sa.Column('class_id', sa.UUID(), nullable=False),
        sa.Column('subject_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['student_id'], ['users.id']),
        sa.ForeignKeyConstraint(['class_id'], ['classes.id']),
        sa.ForeignKeyConstraint(['subject_id'], ['subjects.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_reflections_class_id'), 'reflections', ['class_id'], unique=False)
    op.create_index(op.f('ix_reflections_subject_id'), 'reflections', ['subject_id'], unique=False)

    op.create_table(
        'reflection_clusters',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('representative_text', sa.Text(), nullable=False),
        sa.Column('cluster_size', sa.Integer(), nullable=False),
        sa.Column('computed_at', sa.DateTime(), nullable=False),
        sa.Column('class_id', sa.UUID(), nullable=False),
        sa.Column('subject_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['class_id'], ['classes.id']),
        sa.ForeignKeyConstraint(['subject_id'], ['subjects.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_reflection_clusters_class_id'), 'reflection_clusters', ['class_id'], unique=False)
    op.create_index(op.f('ix_reflection_clusters_subject_id'), 'reflection_clusters', ['subject_id'], unique=False)

    op.create_table(
        'video_recommendation_cache',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('topic', sa.String(length=500), nullable=False),
        sa.Column('videos_json', sa.Text(), nullable=False),
        sa.Column('fetched_at', sa.DateTime(), nullable=False),
        sa.Column('subject_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['subject_id'], ['subjects.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('subject_id', 'topic', name='uq_video_cache_subject_topic'),
    )


def downgrade() -> None:
    op.drop_table('video_recommendation_cache')
    op.drop_index(op.f('ix_reflection_clusters_subject_id'), table_name='reflection_clusters')
    op.drop_index(op.f('ix_reflection_clusters_class_id'), table_name='reflection_clusters')
    op.drop_table('reflection_clusters')
    op.drop_index(op.f('ix_reflections_subject_id'), table_name='reflections')
    op.drop_index(op.f('ix_reflections_class_id'), table_name='reflections')
    op.drop_table('reflections')
