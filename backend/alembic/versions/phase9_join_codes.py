"""phase9_join_codes

Adds a join_code column to the classes table.

Each class gets a unique, human-readable 8-character code (uppercase alphanumeric)
that educators share with students. Students must supply the correct code when
enrolling in a class via the browse panel.

Steps:
  1. Add join_code as nullable.
  2. Populate every existing class with a unique code generated via Python's secrets module.
  3. Set the column NOT NULL.
  4. Add a UNIQUE constraint.
"""

import secrets
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "phase9_join_codes"
down_revision: Union[str, None] = "phase8_enrollment_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def upgrade() -> None:
    bind = op.get_bind()

    # ── Step 1: add nullable column ──────────────────────────────────────────
    op.add_column("classes", sa.Column("join_code", sa.String(10), nullable=True))

    # ── Step 2: populate existing rows with unique codes ─────────────────────
    rows = bind.execute(text("SELECT id FROM classes")).fetchall()
    used_codes = set()
    for row in rows:
        while True:
            code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
            if code not in used_codes:
                used_codes.add(code)
                break
        bind.execute(
            text("UPDATE classes SET join_code = :code WHERE id = :id"),
            {"code": code, "id": row[0]},
        )

    # ── Step 3: make NOT NULL ────────────────────────────────────────────────
    op.alter_column("classes", "join_code", nullable=False)

    # ── Step 4: add unique constraint ────────────────────────────────────────
    op.create_unique_constraint("uq_classes_join_code", "classes", ["join_code"])
    print(f"[phase9] join_code column added and populated for {len(rows)} class(es).")


def downgrade() -> None:
    op.drop_constraint("uq_classes_join_code", "classes", type_="unique")
    op.drop_column("classes", "join_code")
