"""Phase 17: Document Ingestion Lifecycle, Provenance, and Curriculum Review

Revision ID: phase17_doc_ingest_lifecycle
Revises: phase16_quiz_foundation
Create Date: 2026-10-31 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "phase17_doc_ingest_lifecycle"
down_revision = "phase16_quiz_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add 'review_required' to documentstatus enum if not present
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'documentstatus') THEN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_enum
                    WHERE enumlabel = 'review_required'
                      AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'documentstatus')
                ) THEN
                    ALTER TYPE documentstatus ADD VALUE 'review_required';
                END IF;
            END IF;
        END$$;
        """
    )

    # 2. Add columns to documents
    op.add_column("documents", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column(
        "documents",
        sa.Column(
            "processing_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=True,
        ),
    )

    # 3. Add provenance columns to chunks
    op.add_column("chunks", sa.Column("page_number", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("section_heading", sa.String(length=500), nullable=True))

    # 4. Add provenance and review columns to prerequisite_map
    op.add_column(
        "prerequisite_map",
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("prerequisite_map", sa.Column("source_page_number", sa.Integer(), nullable=True))
    op.add_column(
        "prerequisite_map",
        sa.Column("review_status", sa.String(length=50), server_default="approved", nullable=False),
    )
    op.create_foreign_key(
        "fk_prerequisite_map_source_document",
        "prerequisite_map",
        "documents",
        ["source_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_prerequisite_map_source_document_id",
        "prerequisite_map",
        ["source_document_id"],
    )

    # 5. Add provenance and review columns to syllabus_subtopics
    op.add_column(
        "syllabus_subtopics",
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("syllabus_subtopics", sa.Column("source_page_number", sa.Integer(), nullable=True))
    op.add_column(
        "syllabus_subtopics",
        sa.Column("review_status", sa.String(length=50), server_default="approved", nullable=False),
    )
    op.create_foreign_key(
        "fk_syllabus_subtopics_source_document",
        "syllabus_subtopics",
        "documents",
        ["source_document_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 6. Add provenance and review columns to learning_objectives
    op.add_column(
        "learning_objectives",
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("learning_objectives", sa.Column("source_page_number", sa.Integer(), nullable=True))
    op.add_column(
        "learning_objectives",
        sa.Column("review_status", sa.String(length=50), server_default="approved", nullable=False),
    )
    op.add_column(
        "learning_objectives",
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_foreign_key(
        "fk_learning_objectives_source_document",
        "learning_objectives",
        "documents",
        ["source_document_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # 6. Drop learning_objectives columns and FK
    op.drop_constraint("fk_learning_objectives_source_document", "learning_objectives", type_="foreignkey")
    op.drop_column("learning_objectives", "updated_at")
    op.drop_column("learning_objectives", "review_status")
    op.drop_column("learning_objectives", "source_page_number")
    op.drop_column("learning_objectives", "source_document_id")

    # 5. Drop syllabus_subtopics columns and FK
    op.drop_constraint("fk_syllabus_subtopics_source_document", "syllabus_subtopics", type_="foreignkey")
    op.drop_column("syllabus_subtopics", "review_status")
    op.drop_column("syllabus_subtopics", "source_page_number")
    op.drop_column("syllabus_subtopics", "source_document_id")

    # 4. Drop prerequisite_map columns, index, and FK
    op.drop_index("ix_prerequisite_map_source_document_id", table_name="prerequisite_map")
    op.drop_constraint("fk_prerequisite_map_source_document", "prerequisite_map", type_="foreignkey")
    op.drop_column("prerequisite_map", "review_status")
    op.drop_column("prerequisite_map", "source_page_number")
    op.drop_column("prerequisite_map", "source_document_id")

    # 3. Drop chunks columns
    op.drop_column("chunks", "section_heading")
    op.drop_column("chunks", "page_number")

    # 2. Drop documents columns
    op.drop_column("documents", "processing_metadata")
    op.drop_column("documents", "error_message")
