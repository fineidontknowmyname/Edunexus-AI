"""initial_schema_pgvector

Revision ID: a1b2c3d4e5f6
Revises: None
Create Date: 2026-08-17 00:00:00.000000

Baseline schema for Neon PostgreSQL + pgvector — all 18 tables from the
reference design, migrated once per the Shared Foundation Rule (see
EduNexus_AI_CONTEXT.md §13). Replaces an earlier SQLite-era migration that
had drifted out of sync with models/db.py and was never applied to any
real database.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enable pgvector extension (Neon has it pre-installed, just needs enabling) ──
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── users ──────────────────────────────────────────────────────────────────
    op.create_table(
        'users',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column('role', sa.Enum('student', 'educator', 'admin', name='userrole'), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # ── classes ────────────────────────────────────────────────────────────────
    op.create_table(
        'classes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=500), nullable=False),
        sa.Column('subject', sa.String(length=255), nullable=True),
        sa.Column('semester', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('educator_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['educator_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── class_enrollments ─────────────────────────────────────────────────────
    op.create_table(
        'class_enrollments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('class_id', sa.UUID(), nullable=False),
        sa.Column('student_id', sa.UUID(), nullable=False),
        sa.Column('enrolled_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['class_id'], ['classes.id']),
        sa.ForeignKeyConstraint(['student_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── documents ──────────────────────────────────────────────────────────────
    op.create_table(
        'documents',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('filename', sa.String(length=500), nullable=False),
        sa.Column('file_path', sa.String(length=1000), nullable=False),
        sa.Column('subject', sa.String(length=255), nullable=True),
        sa.Column('unit', sa.Integer(), nullable=True),
        sa.Column('chapter', sa.Integer(), nullable=True),
        sa.Column('chapter_name', sa.String(length=500), nullable=True),
        sa.Column('status', sa.Enum('pending', 'processing', 'ready', 'failed', name='documentstatus'), nullable=False),
        sa.Column('is_indexed', sa.Boolean(), nullable=False),
        sa.Column('chunk_count', sa.Integer(), nullable=True),
        sa.Column('deleted', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('class_id', sa.UUID(), nullable=False),
        sa.Column('uploaded_by_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['class_id'], ['classes.id']),
        sa.ForeignKeyConstraint(['uploaded_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── chunks ─────────────────────────────────────────────────────────────────
    op.create_table(
        'chunks',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('contextual_prefix', sa.Text(), nullable=False),
        sa.Column('full_text', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(384), nullable=False),
        sa.Column('subject', sa.String(length=255), nullable=True),
        sa.Column('unit', sa.Integer(), nullable=True),
        sa.Column('chapter', sa.Integer(), nullable=True),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('token_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    # HNSW index for cosine-similarity ANN search — created via raw SQL since
    # Alembic's op.create_index doesn't support the `vector_cosine_ops` operator class.
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    # ── response_cache ─────────────────────────────────────────────────────────
    op.create_table(
        'response_cache',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('query_embedding', Vector(384), nullable=False),
        sa.Column('subject', sa.String(length=255), nullable=True),
        sa.Column('chapter', sa.Integer(), nullable=True),
        sa.Column('context_tier', sa.Enum('strong', 'moderate_weak', 'significant_gaps', name='contexttier'), nullable=False),
        sa.Column('response_text', sa.Text(), nullable=False),
        sa.Column('chunk_ids_used', postgresql.ARRAY(sa.UUID()), nullable=True),
        sa.Column('source_type', sa.Enum('curriculum', 'general_knowledge', name='sourcetype'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.execute(
        "CREATE INDEX ix_response_cache_embedding_hnsw ON response_cache "
        "USING hnsw (query_embedding vector_cosine_ops)"
    )

    # ── class_context ──────────────────────────────────────────────────────────
    op.create_table(
        'class_context',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('class_id', sa.UUID(), nullable=False),
        sa.Column('syllabus_json', sa.Text(), nullable=True),
        sa.Column('assessments_json', sa.Text(), nullable=True),
        sa.Column('teacher_emphasis', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['class_id'], ['classes.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('class_id'),
    )

    # ── topic_mastery ──────────────────────────────────────────────────────────
    op.create_table(
        'topic_mastery',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('topic', sa.String(length=500), nullable=False),
        sa.Column('unit', sa.Integer(), nullable=True),
        sa.Column('mastery_score', sa.Float(), nullable=False),
        sa.Column('attempt_count', sa.Integer(), nullable=False),
        sa.Column('last_attempt_at', sa.DateTime(), nullable=True),
        sa.Column('trend', sa.Enum('improving', 'stable', 'declining', 'not_started', name='masterytrend'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('student_id', sa.UUID(), nullable=False),
        sa.Column('class_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['class_id'], ['classes.id']),
        sa.ForeignKeyConstraint(['student_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_topic_mastery_topic'), 'topic_mastery', ['topic'], unique=False)

    # ── quizzes (created before misconceptions/quiz_attempts due to FK order) ──
    op.create_table(
        'quizzes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('unit', sa.Integer(), nullable=True),
        sa.Column('chapter', sa.Integer(), nullable=True),
        sa.Column('generation_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.Enum('pending_review', 'approved', 'rejected', name='reviewstatus'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('class_id', sa.UUID(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=True),
        sa.Column('created_by_id', sa.UUID(), nullable=True),
        sa.Column('reviewed_by_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['class_id'], ['classes.id']),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id']),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.ForeignKeyConstraint(['reviewed_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── quiz_questions ─────────────────────────────────────────────────────────
    op.create_table(
        'quiz_questions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('question_text', sa.Text(), nullable=False),
        sa.Column('options', sa.Text(), nullable=False),
        sa.Column('correct_answer', sa.Text(), nullable=False),
        sa.Column('difficulty', sa.Enum('easy', 'medium', 'hard', name='questiondifficulty'), nullable=False),
        sa.Column('status', sa.Enum('pending_review', 'approved', 'rejected', name='reviewstatus', create_type=False), nullable=False),
        sa.Column('quiz_id', sa.UUID(), nullable=False),
        sa.Column('source_chunk_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['quiz_id'], ['quizzes.id']),
        sa.ForeignKeyConstraint(['source_chunk_id'], ['chunks.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── quiz_attempts ──────────────────────────────────────────────────────────
    op.create_table(
        'quiz_attempts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('answers', sa.Text(), nullable=True),
        sa.Column('topic_scores', sa.Text(), nullable=True),
        sa.Column('completed', sa.Boolean(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('student_id', sa.UUID(), nullable=False),
        sa.Column('quiz_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['quiz_id'], ['quizzes.id']),
        sa.ForeignKeyConstraint(['student_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── misconceptions ─────────────────────────────────────────────────────────
    op.create_table(
        'misconceptions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('topic', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('detected_at', sa.DateTime(), nullable=False),
        sa.Column('resolved', sa.Boolean(), nullable=False),
        sa.Column('student_id', sa.UUID(), nullable=False),
        sa.Column('class_id', sa.UUID(), nullable=False),
        sa.Column('source_quiz_attempt_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['class_id'], ['classes.id']),
        sa.ForeignKeyConstraint(['student_id'], ['users.id']),
        sa.ForeignKeyConstraint(['source_quiz_attempt_id'], ['quiz_attempts.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── interaction_patterns ───────────────────────────────────────────────────
    op.create_table(
        'interaction_patterns',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('topic', sa.String(length=500), nullable=False),
        sa.Column('questions_asked', sa.Integer(), nullable=False),
        sa.Column('last_asked_at', sa.DateTime(), nullable=True),
        sa.Column('student_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['student_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── engagement ─────────────────────────────────────────────────────────────
    op.create_table(
        'engagement',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('current_streak', sa.Integer(), nullable=False),
        sa.Column('longest_streak', sa.Integer(), nullable=False),
        sa.Column('last_interaction_date', sa.Date(), nullable=True),
        sa.Column('staleness_flag', sa.Boolean(), nullable=False),
        sa.Column('total_sessions', sa.Integer(), nullable=False),
        sa.Column('total_messages', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('student_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['student_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('student_id'),
    )

    # ── chat_sessions ──────────────────────────────────────────────────────────
    op.create_table(
        'chat_sessions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('subject', sa.String(length=255), nullable=True),
        sa.Column('mode', sa.Enum('study', 'revision', 'exam_focus', name='sessionmode'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('student_id', sa.UUID(), nullable=False),
        sa.Column('class_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['class_id'], ['classes.id']),
        sa.ForeignKeyConstraint(['student_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── chat_messages ──────────────────────────────────────────────────────────
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('source_type', sa.Enum('curriculum', 'general_knowledge', name='sourcetype', create_type=False), nullable=True),
        sa.Column('chunk_ids_used', postgresql.ARRAY(sa.UUID()), nullable=True),
        sa.Column('flagged_by_student', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('session_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── educator_notes ─────────────────────────────────────────────────────────
    op.create_table(
        'educator_notes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('educator_id', sa.UUID(), nullable=False),
        sa.Column('student_id', sa.UUID(), nullable=False),
        sa.Column('class_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['class_id'], ['classes.id']),
        sa.ForeignKeyConstraint(['educator_id'], ['users.id']),
        sa.ForeignKeyConstraint(['student_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── prerequisite_map ───────────────────────────────────────────────────────
    # Schema parity only — application code currently reads prerequisites from
    # backend/data/prerequisites_os.json, not this table. See CONTEXT doc log.
    op.create_table(
        'prerequisite_map',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('subject', sa.String(length=255), nullable=False),
        sa.Column('topic', sa.String(length=500), nullable=False),
        sa.Column('requires', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('prerequisite_map')
    op.drop_table('educator_notes')
    op.drop_table('chat_messages')
    op.drop_table('chat_sessions')
    op.drop_table('engagement')
    op.drop_table('interaction_patterns')
    op.drop_table('misconceptions')
    op.drop_table('quiz_attempts')
    op.drop_table('quiz_questions')
    op.drop_table('quizzes')
    op.drop_index(op.f('ix_topic_mastery_topic'), table_name='topic_mastery')
    op.drop_table('topic_mastery')
    op.drop_table('class_context')
    op.execute("DROP INDEX IF EXISTS ix_response_cache_embedding_hnsw")
    op.drop_table('response_cache')
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.drop_table('chunks')
    op.drop_table('documents')
    op.drop_table('class_enrollments')
    op.drop_table('classes')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.execute("DROP EXTENSION IF EXISTS vector")
