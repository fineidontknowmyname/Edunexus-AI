"""Phase 22: Class-scoped engagement, streak expiry, and timezones

Revision ID: phase22_class_engagement
Revises: phase21_question_reports
Create Date: 2026-11-01 12:30:00.000000
"""

from datetime import date, datetime, timedelta, timezone
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "phase22_class_engagement"
down_revision: Union[str, None] = "phase21_question_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def compute_streaks(dates: Union[set[date], list[date]]) -> tuple[int, int, Union[date, None]]:
    """
    Computes (current_streak, longest_streak, last_date) from a set/list of interaction dates.
    - current_streak: length of consecutive day run ending on the latest interaction date (0 if empty).
    - longest_streak: maximum length of any consecutive day run.
    - last_date: latest interaction date (None if empty).
    """
    if not dates:
        return 0, 0, None

    sorted_dates = sorted(set(dates))
    last_date = sorted_dates[-1]

    longest_streak = 1
    current_run = 1

    for i in range(1, len(sorted_dates)):
        if sorted_dates[i] == sorted_dates[i - 1] + timedelta(days=1):
            current_run += 1
        else:
            current_run = 1
        if current_run > longest_streak:
            longest_streak = current_run

    current_streak = current_run
    return current_streak, longest_streak, last_date


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Add users.timezone
    op.add_column(
        "users",
        sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False),
    )

    # 2. Add engagement.class_id as nullable for backfill
    op.add_column(
        "engagement",
        sa.Column("class_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Drop old unique constraint on student_id BEFORE inserting multiple class-scoped rows per student
    conn.execute(sa.text("ALTER TABLE engagement DROP CONSTRAINT IF EXISTS engagement_student_id_key"))
    conn.execute(sa.text("ALTER TABLE engagement DROP CONSTRAINT IF EXISTS uq_engagement_student_id"))

    # 3. Backfill in Python using plain SQL definitions
    enrollment_rows = conn.execute(
        sa.text("SELECT DISTINCT student_id, class_id FROM class_enrollments")
    ).fetchall()

    created_count = 0
    for row in enrollment_rows:
        student_id = row[0]
        class_id = row[1]

        # Collect dates of completed quiz attempts in that class
        quiz_date_rows = conn.execute(
            sa.text(
                """
                SELECT DISTINCT CAST(qa.completed_at AS DATE)
                FROM quiz_attempts qa
                JOIN quizzes q ON qa.quiz_id = q.id
                WHERE qa.student_id = :student_id
                  AND q.class_id = :class_id
                  AND qa.completed = true
                  AND qa.completed_at IS NOT NULL
                """
            ),
            {"student_id": student_id, "class_id": class_id},
        ).fetchall()

        # Collect dates of chat messages sent by the student in chat sessions of that class
        chat_date_rows = conn.execute(
            sa.text(
                """
                SELECT DISTINCT CAST(cm.created_at AS DATE)
                FROM chat_messages cm
                JOIN chat_sessions cs ON cm.session_id = cs.id
                WHERE cs.student_id = :student_id
                  AND cs.class_id = :class_id
                  AND cm.role = 'user'
                  AND cm.created_at IS NOT NULL
                """
            ),
            {"student_id": student_id, "class_id": class_id},
        ).fetchall()

        activity_dates: set[date] = {r[0] for r in quiz_date_rows if r[0] is not None}
        activity_dates.update({r[0] for r in chat_date_rows if r[0] is not None})

        cur_streak, long_streak, last_date = compute_streaks(activity_dates)

        # Count total messages and sessions in that class
        msg_count_res = conn.execute(
            sa.text(
                """
                SELECT COUNT(cm.id)
                FROM chat_messages cm
                JOIN chat_sessions cs ON cm.session_id = cs.id
                WHERE cs.student_id = :student_id
                  AND cs.class_id = :class_id
                  AND cm.role = 'user'
                """
            ),
            {"student_id": student_id, "class_id": class_id},
        ).scalar() or 0

        session_count_res = conn.execute(
            sa.text(
                """
                SELECT COUNT(cs.id)
                FROM chat_sessions cs
                WHERE cs.student_id = :student_id
                  AND cs.class_id = :class_id
                """
            ),
            {"student_id": student_id, "class_id": class_id},
        ).scalar() or 0

        now_utc = datetime.now(timezone.utc)
        conn.execute(
            sa.text(
                """
                INSERT INTO engagement (
                    id, student_id, class_id, current_streak, longest_streak,
                    last_interaction_date, staleness_flag, total_sessions, total_messages,
                    created_at, updated_at
                ) VALUES (
                    :id, :student_id, :class_id, :current_streak, :longest_streak,
                    :last_interaction_date, :staleness_flag, :total_sessions, :total_messages,
                    :created_at, :updated_at
                )
                """
            ),
            {
                "id": uuid.uuid4(),
                "student_id": student_id,
                "class_id": class_id,
                "current_streak": cur_streak,
                "longest_streak": long_streak,
                "last_interaction_date": last_date,
                "staleness_flag": False,
                "total_sessions": session_count_res,
                "total_messages": msg_count_res,
                "created_at": now_utc,
                "updated_at": now_utc,
            },
        )
        created_count += 1

    # Delete old rows with class_id IS NULL
    deleted_count = conn.execute(
        sa.text("DELETE FROM engagement WHERE class_id IS NULL")
    ).rowcount or 0

    print(f"[ALEMBIC phase22] Created {created_count} class-scoped engagement rows, deleted {deleted_count} global rows")

    # 4. Alter engagement.class_id to NOT NULL, create FK and index
    op.alter_column(
        "engagement",
        "class_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_engagement_class_id",
        "engagement",
        "classes",
        ["class_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_engagement_class_id",
        "engagement",
        ["class_id"],
    )

    # 5. Create composite unique constraint
    op.create_unique_constraint(
        "uq_engagement_student_class",
        "engagement",
        ["student_id", "class_id"],
    )


def downgrade() -> None:
    conn = op.get_bind()

    # Drop composite unique constraint
    op.drop_constraint("uq_engagement_student_class", "engagement", type_="unique")

    # Drop FK and index
    op.drop_constraint("fk_engagement_class_id", "engagement", type_="foreignkey")
    op.drop_index("ix_engagement_class_id", table_name="engagement")

    # Collapse rows per student before dropping class_id
    students = conn.execute(
        sa.text("SELECT DISTINCT student_id FROM engagement")
    ).fetchall()

    for s in students:
        student_id = s[0]
        agg = conn.execute(
            sa.text(
                """
                SELECT
                    id,
                    MAX(current_streak) as max_cur,
                    MAX(longest_streak) as max_long,
                    MAX(last_interaction_date) as max_last,
                    SUM(total_messages) as sum_msg,
                    SUM(total_sessions) as sum_sess
                FROM engagement
                WHERE student_id = :student_id
                GROUP BY id
                LIMIT 1
                """
            ),
            {"student_id": student_id},
        ).fetchone()

        if agg:
            # Delete other rows for this student
            conn.execute(
                sa.text("DELETE FROM engagement WHERE student_id = :student_id AND id != :keep_id"),
                {"student_id": student_id, "keep_id": agg[0]},
            )
            # Update the kept row
            conn.execute(
                sa.text(
                    """
                    UPDATE engagement
                    SET current_streak = :cur, longest_streak = :long,
                        last_interaction_date = :last, total_messages = :msg,
                        total_sessions = :sess
                    WHERE id = :keep_id
                    """
                ),
                {
                    "keep_id": agg[0],
                    "cur": agg[1] or 0,
                    "long": agg[2] or 0,
                    "last": agg[3],
                    "msg": agg[4] or 0,
                    "sess": agg[5] or 0,
                },
            )

    op.drop_column("engagement", "class_id")

    # Re-create unique constraint on student_id
    op.create_unique_constraint("engagement_student_id_key", "engagement", ["student_id"])

    # Drop users.timezone
    op.drop_column("users", "timezone")
