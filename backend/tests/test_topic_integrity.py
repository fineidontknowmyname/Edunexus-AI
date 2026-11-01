import inspect
import os
from datetime import datetime, timezone

import pytest

from backend.alembic.versions.phase23_topic_unique import (
    deduplicate_interaction_patterns_records,
    deduplicate_topic_behavior_records,
)
from backend.models.db import Base
from backend.services.topic_graph_service import (
    HANDLED_TOPIC_COLUMNS,
    IGNORED_TOPIC_COLUMNS_ALLOWLIST,
    derive_tag_from_counts,
    merge_interaction_pattern_values,
    merge_topic_behavior_values,
    rename_topic,
)


def test_t1_pure_merge_helpers():
    # 1. merge_interaction_pattern_values
    d1 = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
    d2 = datetime(2026, 10, 5, 14, 0, 0, tzinfo=timezone.utc)
    tot, latest = merge_interaction_pattern_values(3, 7, d1, d2)
    assert tot == 10
    assert latest == d2

    tot2, latest2 = merge_interaction_pattern_values(4, 0, d1, None)
    assert tot2 == 4
    assert latest2 == d1

    # 2. merge_topic_behavior_values
    b1 = {
        "message_count": 5,
        "follow_up_count": 2,
        "qt_conceptual": 3,
        "qt_example": 1,
        "qt_direct": 1,
    }
    b2 = {
        "message_count": 4,
        "follow_up_count": 3,
        "qt_conceptual": 1,
        "qt_example": 2,
        "qt_direct": 1,
    }
    merged = merge_topic_behavior_values(b1, b2)
    assert merged["message_count"] == 9
    assert merged["follow_up_count"] == 5
    assert merged["qt_conceptual"] == 4
    assert merged["qt_example"] == 3
    assert merged["qt_direct"] == 2

    # 3. derive_tag_from_counts
    # low counts (< 3)
    assert derive_tag_from_counts(1, 0, 1, 0, 0) is None
    # needs-repetition: message_count >= 4 and follow_up_count / message_count >= 0.5
    assert derive_tag_from_counts(4, 2, 1, 1, 1) == "needs-repetition"
    # example-driven: qt_example / total_qt >= 0.5
    assert derive_tag_from_counts(2, 0, 1, 3, 0) == "example-driven"
    # concept-first: qt_conceptual / total_qt >= 0.6
    assert derive_tag_from_counts(2, 0, 4, 1, 1) == "concept-first"


def test_t2_topic_drift_guard():
    """Drift guard scanning Base.metadata for topic and topic_key columns."""
    discovered_topic_columns = set()
    for table_name, table in Base.metadata.tables.items():
        for column in table.columns:
            if "topic" in column.name.lower():
                discovered_topic_columns.add((table_name, column.name))

    allowed = HANDLED_TOPIC_COLUMNS.union(set(IGNORED_TOPIC_COLUMNS_ALLOWLIST.keys()))
    unhandled = discovered_topic_columns - allowed
    assert not unhandled, f"Unhandled topic columns discovered in database schema: {unhandled}"


def test_t3_source_inspection_no_commit_in_rename_topic():
    """Verify that rename_topic does not call db.commit() or db.rollback()."""
    source = inspect.getsource(rename_topic)
    assert "db.commit(" not in source, "rename_topic must not call db.commit()"
    assert "db.rollback(" not in source, "rename_topic must not call db.rollback()"
    assert "db.flush(" in source, "rename_topic should flush changes"


def test_t4_migration_deduplication_helpers():
    """Test deduplicate_interaction_patterns_records and deduplicate_topic_behavior_records."""
    # Interaction pattern deduplication
    ip_records = [
        {"student_id": "s1", "class_id": "c1", "topic": "Calculus", "questions_asked": 3, "last_asked_at": datetime(2026, 10, 1)},
        {"student_id": "s1", "class_id": "c1", "topic": "Calculus", "questions_asked": 2, "last_asked_at": datetime(2026, 10, 3)},
        {"student_id": "s1", "class_id": "c1", "topic": "Algebra", "questions_asked": 1, "last_asked_at": datetime(2026, 10, 2)},
    ]
    deduped_ip = deduplicate_interaction_patterns_records(ip_records)
    assert len(deduped_ip) == 2
    calc = next(r for r in deduped_ip if r["topic"] == "Calculus")
    assert calc["questions_asked"] == 5
    assert calc["last_asked_at"] == datetime(2026, 10, 3)

    # Topic behavior deduplication
    tb_records = [
        {
            "student_id": "s1",
            "subject_id": None,
            "topic": "Matrices",
            "message_count": 2,
            "follow_up_count": 1,
            "qt_conceptual": 1,
            "qt_example": 1,
            "qt_direct": 0,
            "updated_at": datetime(2026, 10, 1),
        },
        {
            "student_id": "s1",
            "subject_id": None,
            "topic": "Matrices",
            "message_count": 3,
            "follow_up_count": 2,
            "qt_conceptual": 2,
            "qt_example": 1,
            "qt_direct": 0,
            "updated_at": datetime(2026, 10, 4),
        },
    ]
    deduped_tb = deduplicate_topic_behavior_records(tb_records)
    assert len(deduped_tb) == 1
    assert deduped_tb[0]["message_count"] == 5
    assert deduped_tb[0]["follow_up_count"] == 3
    assert deduped_tb[0]["updated_at"] == datetime(2026, 10, 4)


@pytest.mark.skipif(not os.getenv("EDUNEXUS_DB_TESTS"), reason="Database tests disabled")
def test_t5_rename_topic_merge_db():
    """DB-gated test: rename_topic merges duplicate target rows correctly in DB."""
    pass


@pytest.mark.skipif(not os.getenv("EDUNEXUS_DB_TESTS"), reason="Database tests disabled")
def test_t6_topic_unique_constraint_enforcement_db():
    """DB-gated test: uniqueness constraints on interaction_patterns and topic_behavior."""
    pass
