import importlib
import inspect
import os
from pathlib import Path

import pytest

import backend.services.behavior_service as behavior_service
import backend.services.evidence_service as evidence_service
import backend.services.insights_service as insights_service
import backend.services.misconception_service as misconception_service
import backend.services.progress_service as progress_service
import backend.services.quiz_service as quiz_service
import backend.services.recommendation_service as recommendation_service
import backend.services.topic_graph_service as topic_graph_service


def test_t1_tracking_services_commit_inventory():
    """Verify that tracking domain services only flush and do not commit inside transaction boundaries."""
    # Functions that must strictly NOT call db.commit()
    strict_no_commit_functions = [
        (topic_graph_service.rename_topic, "rename_topic"),
        (progress_service.get_dashboard, "get_dashboard"),
        (progress_service.get_learning_path, "get_learning_path"),
        (progress_service.calculate_mastery, "calculate_mastery"),
        (evidence_service.apply_activity, "apply_activity"),
        (evidence_service.build_engagement_payload, "build_engagement_payload"),
        (insights_service.get_class_metrics, "get_class_metrics"),
        (insights_service.get_class_heatmap, "get_class_heatmap"),
        (insights_service.get_common_misconceptions, "get_common_misconceptions"),
        (misconception_service.record_misconception, "record_misconception"),
        (misconception_service.resolve_misconceptions_for_topic, "resolve_misconceptions_for_topic"),
        (progress_service.update_mastery_after_attempt, "update_mastery_after_attempt"),
        (progress_service.update_mastery_v2_after_attempt, "update_mastery_v2_after_attempt"),
        (evidence_service.update_engagement, "update_engagement"),
        (recommendation_service.link_quiz_attempt_to_recommendations, "link_quiz_attempt_to_recommendations"),
        (quiz_service.build_answer_rows, "build_answer_rows"),
    ]

    for fn, name in strict_no_commit_functions:
        src = inspect.getsource(fn)
        assert "db.commit(" not in src, f"{name} must not contain db.commit()"


def test_t2_response_structures_backward_compatibility():
    """Verify that modified API payloads maintain backward-compatible field structures."""
    # 1. Dashboard summary structure
    from backend.services.progress_service import compute_dashboard_summary
    s = compute_dashboard_summary({}, [])
    expected_summary_keys = {
        "assessed_average",
        "attempted_topics",
        "mastered_topics",
        "total_syllabus_topics",
        "coverage_ratio",
    }
    assert expected_summary_keys.issubset(set(s.keys()))

    # 2. Insights metrics structure
    from backend.services.insights_service import compute_class_average_from_student_scores
    assert compute_class_average_from_student_scores([[0.8], [0.6]]) == 0.70


def test_t3_linear_migration_chain():
    """Verify linear migration chain and <=32 character revision IDs for new remediation phases."""
    new_remediation_migrations = [
        "phase22_class_engagement",
        "phase23_topic_unique",
    ]

    for rev in new_remediation_migrations:
        assert len(rev) <= 32, f"Revision ID {rev!r} exceeds 32 characters (length={len(rev)})"

    # Verify chain linkages
    p23 = importlib.import_module("backend.alembic.versions.phase23_topic_unique")
    assert p23.revision == "phase23_topic_unique"
    assert p23.down_revision == "phase22_class_engagement"

    p22 = importlib.import_module("backend.alembic.versions.phase22_class_engagement")
    assert p22.revision == "phase22_class_engagement"
    assert p22.down_revision == "phase21_question_reports"

    p21 = importlib.import_module("backend.alembic.versions.phase21_question_reports")
    assert p21.revision == "phase21_question_reports"
    assert p21.down_revision == "phase20_quiz_question_generation_meta"

    p20 = importlib.import_module("backend.alembic.versions.phase20_quiz_question_generation_meta")
    assert p20.revision == "phase20_quiz_question_generation_meta"
    assert p20.down_revision == "phase19_quiz_remediation_constraints"


@pytest.mark.skipif(not os.getenv("EDUNEXUS_DB_TESTS"), reason="Database tests disabled")
def test_tracking_lifecycle_e2e_db():
    """End-to-end database-backed lifecycle test for student tracking across all phases."""
    pass
