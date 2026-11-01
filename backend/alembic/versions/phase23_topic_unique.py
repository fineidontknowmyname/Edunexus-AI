"""Phase 23: Topic uniqueness constraints and deduplication

Revision ID: phase23_topic_unique
Revises: phase22_class_engagement
Create Date: 2026-11-01 13:00:00.000000
"""

from datetime import datetime
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "phase23_topic_unique"
down_revision: Union[str, None] = "phase22_class_engagement"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def deduplicate_interaction_patterns_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pure helper for deduplicating interaction_patterns records by (student_id, class_id, topic)."""
    groups: dict[tuple[Any, Any, str], list[dict[str, Any]]] = {}
    for r in records:
        key = (r.get("student_id"), r.get("class_id"), str(r.get("topic", "")).strip())
        groups.setdefault(key, []).append(r)

    merged_records: list[dict[str, Any]] = []
    for key, items in groups.items():
        surviving = dict(items[0])
        total_questions = sum(int(it.get("questions_asked", 0)) for it in items)
        dates = [it.get("last_asked_at") for it in items if it.get("last_asked_at") is not None]
        surviving["questions_asked"] = total_questions
        surviving["last_asked_at"] = max(dates) if dates else None
        merged_records.append(surviving)

    return merged_records


def deduplicate_topic_behavior_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pure helper for deduplicating topic_behavior records where subject_id is None by (student_id, topic)."""
    groups: dict[tuple[Any, str], list[dict[str, Any]]] = {}
    for r in records:
        if r.get("subject_id") is not None:
            continue
        key = (r.get("student_id"), str(r.get("topic", "")).strip())
        groups.setdefault(key, []).append(r)

    merged_records: list[dict[str, Any]] = []
    for key, items in groups.items():
        surviving = dict(items[0])
        surviving["message_count"] = sum(int(it.get("message_count", 0)) for it in items)
        surviving["follow_up_count"] = sum(int(it.get("follow_up_count", 0)) for it in items)
        surviving["qt_conceptual"] = sum(int(it.get("qt_conceptual", 0)) for it in items)
        surviving["qt_example"] = sum(int(it.get("qt_example", 0)) for it in items)
        surviving["qt_direct"] = sum(int(it.get("qt_direct", 0)) for it in items)
        dates = [it.get("updated_at") for it in items if it.get("updated_at") is not None]
        surviving["updated_at"] = max(dates) if dates else None
        merged_records.append(surviving)

    return merged_records


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Deduplicate interaction_patterns
    conn.execute(sa.text("""
        WITH ranked AS (
            SELECT id,
                   student_id,
                   class_id,
                   topic,
                   ROW_NUMBER() OVER (
                       PARTITION BY student_id, class_id, topic
                       ORDER BY last_asked_at DESC NULLS LAST, id
                   ) as rn,
                   SUM(questions_asked) OVER (PARTITION BY student_id, class_id, topic) as total_q,
                   MAX(last_asked_at) OVER (PARTITION BY student_id, class_id, topic) as latest_last
            FROM interaction_patterns
        )
        UPDATE interaction_patterns ip
        SET questions_asked = r.total_q,
            last_asked_at = r.latest_last
        FROM ranked r
        WHERE ip.id = r.id AND r.rn = 1;
    """))

    conn.execute(sa.text("""
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY student_id, class_id, topic
                       ORDER BY last_asked_at DESC NULLS LAST, id
                   ) as rn
            FROM interaction_patterns
        )
        DELETE FROM interaction_patterns
        WHERE id IN (SELECT id FROM ranked WHERE rn > 1);
    """))

    # Create unique constraint on interaction_patterns (student_id, class_id, topic)
    op.create_unique_constraint(
        "uq_interaction_patterns_student_class_topic",
        "interaction_patterns",
        ["student_id", "class_id", "topic"],
    )

    # 2. Deduplicate topic_behavior where subject_id IS NULL
    conn.execute(sa.text("""
        WITH null_subs AS (
            SELECT id,
                   student_id,
                   topic,
                   ROW_NUMBER() OVER (
                       PARTITION BY student_id, topic
                       ORDER BY updated_at DESC NULLS LAST, id
                   ) as rn,
                   SUM(message_count) OVER (PARTITION BY student_id, topic) as tot_m,
                   SUM(follow_up_count) OVER (PARTITION BY student_id, topic) as tot_f,
                   SUM(qt_conceptual) OVER (PARTITION BY student_id, topic) as tot_qc,
                   SUM(qt_example) OVER (PARTITION BY student_id, topic) as tot_qe,
                   SUM(qt_direct) OVER (PARTITION BY student_id, topic) as tot_qd,
                   MAX(updated_at) OVER (PARTITION BY student_id, topic) as latest_up
            FROM topic_behavior
            WHERE subject_id IS NULL
        )
        UPDATE topic_behavior tb
        SET message_count = ns.tot_m,
            follow_up_count = ns.tot_f,
            qt_conceptual = ns.tot_qc,
            qt_example = ns.tot_qe,
            qt_direct = ns.tot_qd,
            updated_at = ns.latest_up
        FROM null_subs ns
        WHERE tb.id = ns.id AND ns.rn = 1;
    """))

    conn.execute(sa.text("""
        WITH null_subs AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY student_id, topic
                       ORDER BY updated_at DESC NULLS LAST, id
                   ) as rn
            FROM topic_behavior
            WHERE subject_id IS NULL
        )
        DELETE FROM topic_behavior
        WHERE id IN (SELECT id FROM null_subs WHERE rn > 1);
    """))

    # Create partial unique index on topic_behavior (student_id, topic) WHERE subject_id IS NULL
    op.create_index(
        "uq_topic_behavior_null_subject",
        "topic_behavior",
        ["student_id", "topic"],
        unique=True,
        postgresql_where=sa.text("subject_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_topic_behavior_null_subject", table_name="topic_behavior")
    op.drop_constraint("uq_interaction_patterns_student_class_topic", "interaction_patterns", type_="unique")
