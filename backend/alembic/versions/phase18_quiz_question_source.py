"""Phase 18: Add source_document_id to quiz_questions

Revision ID: phase18_quiz_question_source
Revises: phase17_doc_ingest_lifecycle
Create Date: 2026-10-31 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "phase18_quiz_question_source"
down_revision = "phase17_doc_ingest_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "quiz_questions",
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_quiz_questions_source_document",
        "quiz_questions",
        "documents",
        ["source_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_quiz_questions_source_document_id",
        "quiz_questions",
        ["source_document_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_quiz_questions_source_document_id", table_name="quiz_questions")
    op.drop_constraint("fk_quiz_questions_source_document", "quiz_questions", type_="foreignkey")
    op.drop_column("quiz_questions", "source_document_id")
