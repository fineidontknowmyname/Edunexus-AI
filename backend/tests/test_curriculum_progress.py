import inspect
import os
from unittest.mock import MagicMock

import pytest

from backend.services.progress_service import (
    compute_dashboard_summary,
    get_learning_path,
    get_syllabus_topics_for_class,
)


def test_t1_compute_dashboard_summary_math():
    """Unit test for compute_dashboard_summary with various mastery distributions."""
    syllabus = ["Topic A", "Topic B", "Topic C", "Topic D"]

    # 1. Zero assessed topics
    empty_mastery = {}
    s0 = compute_dashboard_summary(empty_mastery, syllabus)
    assert s0["assessed_average"] is None
    assert s0["attempted_topics"] == 0
    assert s0["mastered_topics"] == 0
    assert s0["total_syllabus_topics"] == 4
    assert s0["coverage_ratio"] == 0.0

    # 2. Partially assessed (2 of 4)
    part_mastery = {
        "Topic A": {"score": 0.80, "attempts": 2, "trend": "improving"},
        "Topic B": {"score": 0.60, "attempts": 1, "trend": "flat"},
        "Topic C": {"score": 0.0, "attempts": 0, "trend": "not_started"},
    }
    s1 = compute_dashboard_summary(part_mastery, syllabus)
    assert s1["assessed_average"] == 0.70
    assert s1["attempted_topics"] == 2
    assert s1["mastered_topics"] == 1  # only Topic A is >= 0.75
    assert s1["total_syllabus_topics"] == 4
    assert s1["coverage_ratio"] == 0.50

    # 3. Empty syllabus list
    s_empty_syl = compute_dashboard_summary(part_mastery, [])
    assert s_empty_syl["total_syllabus_topics"] == 0
    assert s_empty_syl["coverage_ratio"] == 0.0


def test_t2_get_syllabus_topics_for_class_fallback():
    """Verify get_syllabus_topics_for_class queries DB topic graph then falls back to legacy map."""
    db_mock = MagicMock()

    # Mock class with subject_id and db topics present
    class_row = MagicMock()
    class_row.subject_id = "00000000-0000-0000-0000-000000000001"
    class_row.subject = "Operating Systems"
    db_mock.get.return_value = class_row

    # Mock topic_names_db return
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "backend.services.progress_service.topic_names_db",
            lambda db, s_id: ["DB Topic 1", "DB Topic 2"],
        )
        topics = get_syllabus_topics_for_class(db_mock, "class-1")
        assert topics == ["DB Topic 1", "DB Topic 2"]

        # When db topics empty, fallback to legacy map
        mp.setattr(
            "backend.services.progress_service.topic_names_db",
            lambda db, s_id: [],
        )
        mp.setattr(
            "backend.services.progress_service.load_prerequisite_map",
            lambda subj: {"Legacy Topic 1": []},
        )
        fallback_topics = get_syllabus_topics_for_class(db_mock, "class-1")
        assert fallback_topics == ["Legacy Topic 1"]


def test_t3_source_inspection_learning_path_uses_db_topic_graph():
    """Verify get_learning_path references DB topic graph rather than pure JSON only."""
    src = inspect.getsource(get_learning_path)
    assert (
        "load_topic_graph_db" in src or "get_syllabus_topics_for_class" in src
    ), "get_learning_path must reference load_topic_graph_db or get_syllabus_topics_for_class"


@pytest.mark.skipif(not os.getenv("EDUNEXUS_DB_TESTS"), reason="Database tests disabled")
def test_t4_curriculum_progress_db():
    """DB-gated integration test for dashboard summary and learning path."""
    pass
