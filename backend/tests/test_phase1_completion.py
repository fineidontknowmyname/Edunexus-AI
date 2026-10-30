import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.core.config import Settings
from backend.models.db import Engagement, InteractionPattern, MasteryTrend, TopicMastery
from backend.models.schemas import TopicMasteryRead, TopicMasterySummary, _parse_mastery_v2
from backend.services import progress_service


def test_parse_mastery_v2_helper():
    valid_dict = {"mastery_estimate": 0.85, "mastery_band": "proficient"}
    json_str = '{"mastery_estimate": 0.85, "mastery_band": "proficient"}'

    # JSON string -> dict
    assert _parse_mastery_v2(json_str) == valid_dict

    # dict unchanged
    assert _parse_mastery_v2(valid_dict) == valid_dict

    # None -> None
    assert _parse_mastery_v2(None) is None

    # invalid JSON -> None
    assert _parse_mastery_v2("{corrupt json") is None

    # JSON list -> None
    assert _parse_mastery_v2("[1, 2, 3]") is None

    # empty string -> None
    assert _parse_mastery_v2("") is None
    assert _parse_mastery_v2("   ") is None


def test_schema_from_attributes_with_json_string():
    class FakeTopicMasteryRow:
        def __init__(self, mastery_v2):
            self.id = uuid.uuid4()
            self.topic = "Deadlocks"
            self.unit = 3
            self.mastery_score = 0.90
            self.attempt_count = 5
            self.trend = MasteryTrend.improving
            self.last_attempt_at = None
            self.student_id = uuid.uuid4()
            self.mastery_v2 = mastery_v2

    # Valid JSON string attribute
    row_valid = FakeTopicMasteryRow('{"mastery_estimate": 0.90, "mastery_band": "mastered"}')
    parsed_valid = TopicMasteryRead.model_validate(row_valid)
    assert parsed_valid.mastery_v2 == {"mastery_estimate": 0.90, "mastery_band": "mastered"}
    assert parsed_valid.topic == "Deadlocks"
    assert parsed_valid.mastery_score == 0.90

    # Invalid JSON string attribute -> None (never raise)
    row_corrupt = FakeTopicMasteryRow("not valid json")
    parsed_corrupt = TopicMasteryRead.model_validate(row_corrupt)
    assert parsed_corrupt.mastery_v2 is None

    # None attribute -> None
    row_none = FakeTopicMasteryRow(None)
    parsed_none = TopicMasteryRead.model_validate(row_none)
    assert parsed_none.mastery_v2 is None


def test_dashboard_mastery_v2_exposure():
    student_context = {
        "mastery": {
            "Algorithms": {"score": 0.85, "trend": "improving", "attempts": 4},
            "CorruptTopic": {"score": 0.50, "trend": "stable", "attempts": 2},
            "NoV2Topic": {"score": 0.30, "trend": "declining", "attempts": 1},
        },
        "upcoming_focus": None,
    }

    fake_rows = [
        SimpleNamespace(
            topic="Algorithms",
            mastery_v2='{"mastery_estimate": 0.85, "mastery_band": "proficient"}',
            last_attempt_at=None,
        ),
        SimpleNamespace(
            topic="CorruptTopic",
            mastery_v2='{corrupt: json',
            last_attempt_at=None,
        ),
        SimpleNamespace(
            topic="NoV2Topic",
            mastery_v2=None,
            last_attempt_at=None,
        ),
    ]

    mock_db = MagicMock()

    def query_mock(model):
        q = MagicMock()
        if model is Engagement:
            q.filter.return_value.first.return_value = None
        elif model is InteractionPattern:
            q.filter.return_value.all.return_value = []
        elif model is TopicMastery:
            q.filter.return_value.all.return_value = fake_rows
        return q

    mock_db.query.side_effect = query_mock

    # 1. mastery_v2_enabled = True:
    settings_on = Settings(database_url="sqlite://", mastery_v2_enabled=True)
    with patch("backend.core.config.get_settings", return_value=settings_on), \
         patch("backend.services.context_service.assemble_student_context", return_value=student_context):
        dash = progress_service.get_dashboard(mock_db, "stu_1", "class_1")

    mastery_by_name = {m["topic"]: m for m in dash["mastery"]}

    # Valid JSON gets dict, old keys unchanged
    algo = mastery_by_name["Algorithms"]
    assert algo["topic"] == "Algorithms"
    assert algo["score"] == 0.85
    assert algo["trend"] == "improving"
    assert algo["attempts"] == 4
    assert algo["mastery_v2"] == {
        "mastery_estimate": 0.85,
        "mastery_band": "proficient",
        "evidence_age_days": None,
        "stale": False,
    }

    # Invalid JSON gives None and does not raise
    corrupt = mastery_by_name["CorruptTopic"]
    assert corrupt["topic"] == "CorruptTopic"
    assert corrupt["score"] == 0.50
    assert corrupt["trend"] == "stable"
    assert corrupt["attempts"] == 2
    assert corrupt["mastery_v2"] is None

    # Empty / None v2 gives None
    no_v2 = mastery_by_name["NoV2Topic"]
    assert no_v2["topic"] == "NoV2Topic"
    assert no_v2["score"] == 0.30
    assert no_v2["trend"] == "declining"
    assert no_v2["attempts"] == 1
    assert no_v2["mastery_v2"] is None

    # 2. mastery_v2_enabled = False (flag off):
    settings_off = Settings(database_url="sqlite://", mastery_v2_enabled=False)
    with patch("backend.core.config.get_settings", return_value=settings_off), \
         patch("backend.services.context_service.assemble_student_context", return_value=student_context):
        dash_off = progress_service.get_dashboard(mock_db, "stu_1", "class_1")

    mastery_off_by_name = {m["topic"]: m for m in dash_off["mastery"]}
    assert mastery_off_by_name["Algorithms"] == {
        "topic": "Algorithms",
        "score": 0.85,
        "trend": "improving",
        "attempts": 4,
        "mastery_v2": None,
    }
