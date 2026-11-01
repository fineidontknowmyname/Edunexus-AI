"""Preflight script for tracking migrations (Phase 19-23).

Usage:
    python backend/scripts/preflight_tracking_migrations.py [--apply] [--db-url DB_URL]

Default mode is dry-run (read-only). Pass --apply to perform changes.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.core.config import get_settings


def get_engine(db_url: str | None = None) -> Engine:
    if not db_url:
        settings = get_settings()
        db_url = settings.database_url
    return sa.create_engine(db_url)


def run_preflight(engine: Engine, apply_changes: bool = False) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "apply_mode": apply_changes,
        "users_null_timezone": 0,
        "users_timezone_updated": 0,
        "topic_mastery_duplicate_groups": 0,
        "topic_mastery_rows_removed": 0,
        "engagement_null_class_id": 0,
        "engagement_assigned_single_enrollment": 0,
        "engagement_assigned_recent_attempt": 0,
        "engagement_assigned_earliest_enrollment": 0,
        "engagement_zero_enrollment_deleted": 0,
        "engagement_legacy_rows_backed_up": 0,
    }

    with engine.connect() as conn:
        inspector = sa.inspect(conn)

        # Ensure alembic_version.version_num is wide enough (>= 64 chars) for Phase 19+ revisions
        if "alembic_version" in inspector.get_table_names(schema="public"):
            conn.execute(text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)"))
            if apply_changes:
                conn.commit()

        # -------------------------------------------------------------
        # 1. users.timezone check
        # -------------------------------------------------------------
        user_cols = {col["name"] for col in inspector.get_columns("users", schema="public")}
        if "timezone" in user_cols:
            null_tz = conn.execute(
                text("SELECT COUNT(*) FROM users WHERE timezone IS NULL")
            ).scalar() or 0
            summary["users_null_timezone"] = null_tz
            print(f"[Preflight] users.timezone column exists. NULL count: {null_tz}")
            if apply_changes and null_tz > 0:
                res = conn.execute(
                    text("UPDATE users SET timezone = 'UTC' WHERE timezone IS NULL")
                )
                summary["users_timezone_updated"] = res.rowcount
                print(f"[Preflight] Updated {res.rowcount} users with timezone = 'UTC'.")
        else:
            print("[Preflight] users.timezone column does not exist yet (will be added by migration phase22).")

        # -------------------------------------------------------------
        # 2. topic_mastery duplicate check and deduplication
        # -------------------------------------------------------------
        # Survivor rule: highest attempt_count, tie-break latest last_attempt_at.
        # DO NOT order by UUID id.
        dupe_groups = conn.execute(
            text(
                """
                SELECT student_id, class_id, topic, COUNT(*) as cnt
                FROM topic_mastery
                GROUP BY student_id, class_id, topic
                HAVING COUNT(*) > 1
                """
            )
        ).fetchall()
        summary["topic_mastery_duplicate_groups"] = len(dupe_groups)
        print(f"[Preflight] topic_mastery duplicate groups found: {len(dupe_groups)}")

        if dupe_groups:
            for g in dupe_groups[:5]:
                print(f"  Sample duplicate group: student={g.student_id}, class={g.class_id}, topic='{g.topic}', count={g.cnt}")

            if apply_changes:
                # Ensure backup table exists
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS topic_mastery_dedup_backup (
                            backup_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            backed_up_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            original_id UUID,
                            student_id UUID,
                            class_id UUID,
                            topic VARCHAR(500),
                            unit INTEGER,
                            mastery_score FLOAT,
                            attempt_count INTEGER,
                            last_attempt_at TIMESTAMP,
                            last_quiz_passed BOOLEAN,
                            trend VARCHAR(50),
                            updated_at TIMESTAMP,
                            subject_id UUID,
                            mastery_v2 JSON
                        )
                        """
                    )
                )

                # For each duplicate group, rank survivors by attempt_count DESC, then last_attempt_at DESC NULLS LAST
                # Copy non-survivors (rn > 1) to backup table, then delete them.
                # Notice we order by attempt_count DESC, last_attempt_at DESC NULLS LAST, updated_at DESC NULLS LAST
                # Never order by UUID id.
                backup_sql = text(
                    """
                    WITH ranked AS (
                        SELECT id, student_id, class_id, topic, unit, mastery_score, attempt_count,
                               last_attempt_at, last_quiz_passed, trend, updated_at, subject_id, mastery_v2,
                               ROW_NUMBER() OVER (
                                   PARTITION BY student_id, class_id, topic
                                   ORDER BY attempt_count DESC, last_attempt_at DESC NULLS LAST, updated_at DESC NULLS LAST
                               ) as rn
                        FROM topic_mastery
                    )
                    INSERT INTO topic_mastery_dedup_backup (
                        original_id, student_id, class_id, topic, unit, mastery_score, attempt_count,
                        last_attempt_at, last_quiz_passed, trend, updated_at, subject_id, mastery_v2
                    )
                    SELECT id, student_id, class_id, topic, unit, mastery_score, attempt_count,
                           last_attempt_at, last_quiz_passed, trend, updated_at, subject_id, mastery_v2
                    FROM ranked
                    WHERE rn > 1
                    """
                )
                res_backup = conn.execute(backup_sql)
                rows_to_delete = res_backup.rowcount or 0

                delete_sql = text(
                    """
                    WITH ranked AS (
                        SELECT id,
                               ROW_NUMBER() OVER (
                                   PARTITION BY student_id, class_id, topic
                                   ORDER BY attempt_count DESC, last_attempt_at DESC NULLS LAST, updated_at DESC NULLS LAST
                               ) as rn
                        FROM topic_mastery
                    )
                    DELETE FROM topic_mastery
                    WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
                    """
                )
                res_del = conn.execute(delete_sql)
                summary["topic_mastery_rows_removed"] = res_del.rowcount or 0
                print(f"[Preflight] Deduplicated topic_mastery: backed up and removed {res_del.rowcount} duplicate rows.")

        # -------------------------------------------------------------
        # 3. engagement backup and class_id handling
        # -------------------------------------------------------------
        eng_cols = {col["name"] for col in inspector.get_columns("engagement", schema="public")}

        # Always ensure engagement_legacy_backup exists and has current records before migration
        if apply_changes:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS engagement_legacy_backup (
                        backup_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        backed_up_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        original_id UUID,
                        student_id UUID,
                        current_streak INTEGER,
                        longest_streak INTEGER,
                        last_interaction_date DATE,
                        staleness_flag BOOLEAN,
                        total_sessions INTEGER,
                        total_messages INTEGER,
                        created_at TIMESTAMP,
                        updated_at TIMESTAMP
                    )
                    """
                )
            )
            # Copy rows not already backed up
            conn.execute(
                text(
                    """
                    INSERT INTO engagement_legacy_backup (
                        original_id, student_id, current_streak, longest_streak,
                        last_interaction_date, staleness_flag, total_sessions, total_messages,
                        created_at, updated_at
                    )
                    SELECT id, student_id, current_streak, longest_streak,
                           last_interaction_date, staleness_flag, total_sessions, total_messages,
                           created_at, updated_at
                    FROM engagement
                    WHERE id NOT IN (SELECT original_id FROM engagement_legacy_backup WHERE original_id IS NOT NULL)
                    """
                )
            )
            backed_up_cnt = conn.execute(text("SELECT COUNT(*) FROM engagement_legacy_backup")).scalar() or 0
            summary["engagement_legacy_rows_backed_up"] = backed_up_cnt
            print(f"[Preflight] engagement_legacy_backup verified ({backed_up_cnt} rows total).")

        if "class_id" in eng_cols:
            null_class_rows = conn.execute(
                text("SELECT id, student_id FROM engagement WHERE class_id IS NULL")
            ).fetchall()
            summary["engagement_null_class_id"] = len(null_class_rows)
            print(f"[Preflight] engagement rows with NULL class_id: {len(null_class_rows)}")

            for row in null_class_rows:
                eng_id = row.id
                st_id = row.student_id

                enrollments = conn.execute(
                    text(
                        """
                        SELECT class_id, enrolled_at
                        FROM class_enrollments
                        WHERE student_id = :student_id
                        ORDER BY enrolled_at ASC
                        """
                    ),
                    {"student_id": st_id},
                ).fetchall()

                if len(enrollments) == 1:
                    target_class = enrollments[0].class_id
                    summary["engagement_assigned_single_enrollment"] += 1
                    if apply_changes:
                        conn.execute(
                            text("UPDATE engagement SET class_id = :cid WHERE id = :eid"),
                            {"cid": target_class, "eid": eng_id},
                        )
                elif len(enrollments) > 1:
                    # Look for most recent QuizAttempt
                    recent_quiz_class = conn.execute(
                        text(
                            """
                            SELECT q.class_id
                            FROM quiz_attempts qa
                            JOIN quizzes q ON qa.quiz_id = q.id
                            WHERE qa.student_id = :student_id
                              AND qa.completed = true
                              AND qa.completed_at IS NOT NULL
                            ORDER BY qa.completed_at DESC
                            LIMIT 1
                            """
                        ),
                        {"student_id": st_id},
                    ).scalar()

                    if recent_quiz_class is not None:
                        target_class = recent_quiz_class
                        summary["engagement_assigned_recent_attempt"] += 1
                    else:
                        target_class = enrollments[0].class_id
                        summary["engagement_assigned_earliest_enrollment"] += 1

                    if apply_changes:
                        conn.execute(
                            text("UPDATE engagement SET class_id = :cid WHERE id = :eid"),
                            {"cid": target_class, "eid": eng_id},
                        )
                else:
                    # Zero enrollments: copy to backup (already done above) and delete row
                    summary["engagement_zero_enrollment_deleted"] += 1
                    if apply_changes:
                        conn.execute(
                            text("DELETE FROM engagement WHERE id = :eid"),
                            {"eid": eng_id},
                        )
        else:
            print("[Preflight] engagement.class_id column does not exist yet (will be added and populated by migration phase22).")

        if apply_changes:
            conn.commit()
            print("[Preflight] All changes committed successfully.")
        else:
            print("[Preflight] Dry-run complete. No changes made to database.")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Preflight check and migration support script")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default is dry-run)")
    parser.add_argument("--db-url", type=str, default=None, help="Database URL override")
    args = parser.parse_args()

    engine = get_engine(args.db_url)
    res = run_preflight(engine, apply_changes=args.apply)
    print("\n--- Preflight Summary ---")
    for k, v in res.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
