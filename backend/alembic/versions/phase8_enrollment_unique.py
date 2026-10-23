"""phase8_enrollment_unique

Adds a UNIQUE constraint on class_enrollments(class_id, student_id).

Before adding the constraint:
  1. Runs a read-only preflight that prints any duplicate (class_id, student_id)
     pairs so there is a visible audit trail before any mutation.
  2. Deletes duplicate rows, keeping the row with the lexicographically smallest
     UUID string as the tie-breaker (arbitrary but deterministic).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "phase8_enrollment_unique"
down_revision: Union[str, None] = "phase7_hardening"  # single current head
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # ── Step 1: read-only preflight ──────────────────────────────────────────
    result = bind.execute(
        text(
            """
            SELECT class_id, student_id, COUNT(*) AS cnt
            FROM class_enrollments
            GROUP BY class_id, student_id
            HAVING COUNT(*) > 1
            """
        )
    )
    dupes = result.fetchall()
    print(f"[phase8] Duplicate enrollment pairs found: {len(dupes)}")
    for row in dupes:
        print(f"  class_id={row.class_id}  student_id={row.student_id}  count={row.cnt}")

    # ── Step 2: delete duplicates, keep the row with MIN(id::text) ───────────
    if dupes:
        bind.execute(
            text(
                """
                DELETE FROM class_enrollments
                WHERE id NOT IN (
                    SELECT MIN(id::text)::uuid
                    FROM class_enrollments
                    GROUP BY class_id, student_id
                )
                """
            )
        )
        print("[phase8] Duplicate rows removed; kept the row with the lowest UUID per pair.")

    # ── Step 3: add unique constraint ────────────────────────────────────────
    op.create_unique_constraint(
        "uq_class_enrollments_class_student",
        "class_enrollments",
        ["class_id", "student_id"],
    )
    print("[phase8] Unique constraint uq_class_enrollments_class_student created.")


def downgrade() -> None:
    op.drop_constraint(
        "uq_class_enrollments_class_student",
        "class_enrollments",
        type_="unique",
    )
