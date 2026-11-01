"""Phase 19: Quiz remediation constraints

Revision ID: phase19_quiz_remediation_constraints
Revises: phase18_quiz_question_source
Create Date: 2026-10-31 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "phase19_quiz_remediation_constraints"
down_revision: Union[str, None] = "phase18_quiz_question_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # ── W7: Misconception FK ondelete='SET NULL' ─────────────────────────────
    # Drop existing foreign key on misconceptions.source_quiz_attempt_id if exists
    bind.execute(
        text("ALTER TABLE misconceptions DROP CONSTRAINT IF EXISTS misconceptions_source_quiz_attempt_id_fkey")
    )
    bind.execute(
        text("ALTER TABLE misconceptions DROP CONSTRAINT IF EXISTS fk_misconceptions_source_quiz_attempt_id")
    )

    op.create_foreign_key(
        "fk_misconceptions_source_quiz_attempt_id",
        "misconceptions",
        "quiz_attempts",
        ["source_quiz_attempt_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ── W8: TopicMastery unique constraint (student_id, class_id, topic) ─────
    # Preflight duplicate check: do NOT delete user data; abort if duplicates exist
    result = bind.execute(
        text(
            """
            SELECT student_id, class_id, topic, COUNT(*) AS cnt
            FROM topic_mastery
            GROUP BY student_id, class_id, topic
            HAVING COUNT(*) > 1
            """
        )
    )
    dupes = result.fetchall()
    if dupes:
        dupe_details = [
            f"(student_id={r.student_id}, class_id={r.class_id}, topic='{r.topic}', count={r.cnt})"
            for r in dupes
        ]
        raise RuntimeError(
            f"Cannot apply unique constraint uq_topic_mastery_student_class_topic. "
            f"Found {len(dupes)} duplicate tuple(s) in topic_mastery: {', '.join(dupe_details)}. "
            "Please resolve duplicates manually before running this migration."
        )

    op.create_unique_constraint(
        "uq_topic_mastery_student_class_topic",
        "topic_mastery",
        ["student_id", "class_id", "topic"],
    )


def downgrade() -> None:
    # Drop unique constraint on topic_mastery
    try:
        op.drop_constraint(
            "uq_topic_mastery_student_class_topic",
            "topic_mastery",
            type_="unique",
        )
    except Exception:
        pass

    # Restore default FK without ondelete='SET NULL'
    try:
        op.drop_constraint(
            "fk_misconceptions_source_quiz_attempt_id",
            "misconceptions",
            type_="foreignkey",
        )
    except Exception:
        pass

    op.create_foreign_key(
        "misconceptions_source_quiz_attempt_id_fkey",
        "misconceptions",
        "quiz_attempts",
        ["source_quiz_attempt_id"],
        ["id"],
    )
