from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import importlib.util
import inspect
import os
from pathlib import Path
from typing import Any
import uuid

import pytest

from backend.core.time_utils import (
    capture_client_timezone,
    effective_streak,
    is_valid_timezone,
    local_today,
)
from backend.core.tracking_constants import ENGAGEMENT_INACTIVE_DAYS
from backend.models.db import (
    Class,
    ClassEnrollment,
    Engagement,
    Quiz,
    QuizQuestion,
    ReviewStatus,
    User,
    UserRole,
)
from backend.services import evidence_service, progress_service

DB_TEST_REASON = (
    "Database-backed integration test skipped by default. "
    "Run only against a confirmed disposable Neon database branch by setting EDUNEXUS_DB_TESTS=1."
)


# Helper dataclass representing engagement for pure logic tests
@dataclass
class FakeEngagement:
    current_streak: int = 0
    longest_streak: int = 0
    last_interaction_date: date | None = None
    staleness_flag: bool = False
    total_sessions: int = 0
    total_messages: int = 0


# ==============================================================================
# T1: time_utils unit tests
# ==============================================================================


def test_t1_time_utils_local_today_and_effective_streak():
    """T1 (No DB): Tests local_today fallback and effective_streak boundary conditions."""
    fixed_utc = datetime(2026, 11, 1, 15, 0, 0, tzinfo=timezone.utc)

    # Valid zone (Asia/Kolkata is UTC+5:30 -> 20:30 on Nov 1)
    assert local_today("Asia/Kolkata", fixed_utc) == date(2026, 11, 1)

    # Valid zone where date crosses midnight (Pacific/Auckland is UTC+13 -> Nov 2)
    assert local_today("Pacific/Auckland", fixed_utc) == date(2026, 11, 2)

    # Invalid zone, empty zone, None fallback to UTC
    assert local_today("Invalid/Timezone", fixed_utc) == date(2026, 11, 1)
    assert local_today("", fixed_utc) == date(2026, 11, 1)
    assert local_today(None, fixed_utc) == date(2026, 11, 1)

    # is_valid_timezone
    assert is_valid_timezone("America/New_York") is True
    assert is_valid_timezone("UTC") is True
    assert is_valid_timezone("Fake/Zone") is False
    assert is_valid_timezone(None) is False
    assert is_valid_timezone("") is False

    # effective_streak
    today = date(2026, 11, 1)
    assert effective_streak(5, None, today) == 0
    assert effective_streak(5, today, today) == 5
    assert effective_streak(5, today - timedelta(days=1), today) == 5
    assert effective_streak(5, today - timedelta(days=2), today) == 0
    assert effective_streak(5, today - timedelta(days=7), today) == 0
    # Future / clock backwards
    assert effective_streak(5, today + timedelta(days=1), today) == 5


# ==============================================================================
# T2: apply_activity pure mutation tests
# ==============================================================================


def test_t2_apply_activity_mutation_logic():
    """T2 (No DB): Tests streak progression, gap resets, same-day, and clock backwards."""
    eng = FakeEngagement(staleness_flag=True)
    d1 = date(2026, 11, 1)
    d2 = date(2026, 11, 2)
    d5 = date(2026, 11, 5)
    d4 = date(2026, 11, 4)

    # First activity: streak becomes 1, longest 1, staleness cleared
    evidence_service.apply_activity(eng, d1, count_as_message=True)
    assert eng.current_streak == 1
    assert eng.longest_streak == 1
    assert eng.last_interaction_date == d1
    assert eng.total_messages == 1
    assert eng.staleness_flag is False

    # Same day activity: streak unchanged, messages incremented
    evidence_service.apply_activity(eng, d1, count_as_message=True)
    assert eng.current_streak == 1
    assert eng.longest_streak == 1
    assert eng.last_interaction_date == d1
    assert eng.total_messages == 2

    # Consecutive day: streak increments to 2, longest to 2
    evidence_service.apply_activity(eng, d2, count_as_message=False)
    assert eng.current_streak == 2
    assert eng.longest_streak == 2
    assert eng.last_interaction_date == d2
    assert eng.total_messages == 2

    # Missed days (gap to d5): streak resets to 1, longest preserved at 2
    evidence_service.apply_activity(eng, d5, count_as_message=True)
    assert eng.current_streak == 1
    assert eng.longest_streak == 2
    assert eng.last_interaction_date == d5
    assert eng.total_messages == 3

    # Clock moved backwards (d4 < last_interaction_date d5): streak & date preserved
    evidence_service.apply_activity(eng, d4, count_as_message=True)
    assert eng.current_streak == 1
    assert eng.longest_streak == 2
    assert eng.last_interaction_date == d5
    assert eng.total_messages == 4


# ==============================================================================
# T3: Timezone boundary condition (Asia/Kolkata)
# ==============================================================================


def test_t3_timezone_boundary_consecutive_days():
    """T3 (No DB): Late evening day D and early morning day D+1 in Asia/Kolkata give consecutive streak."""
    # Day D late night: 23:30 local IST is 18:00 UTC
    instant1_utc = datetime(2026, 11, 1, 18, 0, 0, tzinfo=timezone.utc)
    # Day D+1 morning: 09:00 local IST is 03:30 UTC
    instant2_utc = datetime(2026, 11, 2, 3, 30, 0, tzinfo=timezone.utc)

    local_d1 = local_today("Asia/Kolkata", instant1_utc)
    local_d2 = local_today("Asia/Kolkata", instant2_utc)

    assert local_d1 == date(2026, 11, 1)
    assert local_d2 == date(2026, 11, 2)
    assert (local_d2 - local_d1).days == 1

    eng = FakeEngagement()
    evidence_service.apply_activity(eng, local_d1, count_as_message=True)
    assert eng.current_streak == 1

    evidence_service.apply_activity(eng, local_d2, count_as_message=True)
    assert eng.current_streak == 2
    assert eng.longest_streak == 2


# ==============================================================================
# T4: compute_streaks from migration file
# ==============================================================================


def test_t4_migration_compute_streaks():
    """T4 (No DB): Imports compute_streaks directly from migration and tests algorithm."""
    migration_path = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "phase22_class_engagement.py"
    spec = importlib.util.spec_from_file_location("phase22_class_engagement", str(migration_path))
    assert spec is not None and spec.loader is not None
    migration_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration_mod)

    compute_streaks = migration_mod.compute_streaks

    # Empty
    assert compute_streaks([]) == (0, 0, None)
    assert compute_streaks(set()) == (0, 0, None)

    # Consecutive run
    d1 = date(2026, 10, 1)
    d2 = date(2026, 10, 2)
    d3 = date(2026, 10, 3)
    assert compute_streaks([d1, d2, d3]) == (3, 3, d3)

    # Gap: run of 3, gap, then run of 2 ending on last date
    d10 = date(2026, 10, 10)
    d11 = date(2026, 10, 11)
    cur, longest, last = compute_streaks([d1, d2, d3, d10, d11])
    assert cur == 2
    assert longest == 3
    assert last == d11

    # Single date
    assert compute_streaks([d1]) == (1, 1, d1)


# ==============================================================================
# T5: Source inspection: no commits in evidence_service functions
# ==============================================================================


def test_t5_source_inspection_no_commits_in_engagement_service():
    """T5 (No DB): Asserts update_engagement and get_or_create_engagement contain no db.commit()."""
    target_funcs = [
        evidence_service.update_engagement,
        evidence_service.get_or_create_engagement,
    ]
    for func in target_funcs:
        src = inspect.getsource(func)
        assert "db.commit(" not in src, f"{func.__name__} must not commit"


# ==============================================================================
# T6: build_engagement_payload read-only tests
# ==============================================================================


def test_t6_build_engagement_payload():
    """T6 (No DB): Verifies read-only payload calculation, staleness, and streak expiry."""
    today = date(2026, 11, 1)

    # None row
    p_none = evidence_service.build_engagement_payload(None, today)
    assert p_none["current_streak"] == 0
    assert p_none["longest_streak"] == 0
    assert p_none["has_activity"] is False
    assert p_none["is_inactive"] is False
    assert p_none["staleness_flag"] is False

    # Yesterday activity: active, streak retained, not inactive
    yesterday = today - timedelta(days=1)
    eng_recent = FakeEngagement(current_streak=4, longest_streak=7, last_interaction_date=yesterday, total_messages=12, total_sessions=3)
    p_recent = evidence_service.build_engagement_payload(eng_recent, today)
    assert p_recent["current_streak"] == 4
    assert p_recent["longest_streak"] == 7
    assert p_recent["has_activity"] is True
    assert p_recent["is_inactive"] is False
    assert p_recent["staleness_flag"] is False

    # Activity 6 days ago (>= ENGAGEMENT_INACTIVE_DAYS): inactive, streak decayed to 0 on read
    six_days_ago = today - timedelta(days=6)
    eng_stale = FakeEngagement(current_streak=4, longest_streak=7, last_interaction_date=six_days_ago)
    p_stale = evidence_service.build_engagement_payload(eng_stale, today)
    assert p_stale["current_streak"] == 0
    assert p_stale["longest_streak"] == 7
    assert p_stale["has_activity"] is True
    assert p_stale["is_inactive"] is True
    assert p_stale["staleness_flag"] is True


# ==============================================================================
# T7 & T8: Database-backed tests (skipped unless EDUNEXUS_DB_TESTS=1)
# ==============================================================================


@pytest.mark.skipif(os.getenv("EDUNEXUS_DB_TESTS") != "1", reason=DB_TEST_REASON)
def test_t7_class_scoped_engagement_isolation(client, db, student_user, educator_user):
    """T7 (Needs DB): Activity in Class A does not alter Class B's engagement row or payload."""
    c1 = Class(name="Class Alpha", subject="CS", join_code=uuid.uuid4().hex[:8], educator_id=educator_user.id)
    c2 = Class(name="Class Beta", subject="Math", join_code=uuid.uuid4().hex[:8], educator_id=educator_user.id)
    db.add_all([c1, c2])
    db.commit()

    db.add_all([
        ClassEnrollment(class_id=c1.id, student_id=student_user.id),
        ClassEnrollment(class_id=c2.id, student_id=student_user.id),
    ])
    db.commit()

    # Trigger engagement update in Class Alpha only
    evidence_service.update_engagement(db, student_user.id, c1.id, count_as_message=True)
    db.commit()

    row_c1 = db.query(Engagement).filter(Engagement.student_id == student_user.id, Engagement.class_id == c1.id).first()
    row_c2 = db.query(Engagement).filter(Engagement.student_id == student_user.id, Engagement.class_id == c2.id).first()

    assert row_c1 is not None
    assert row_c1.current_streak == 1
    assert row_c1.total_messages == 1

    # Class Beta has zero engagement row
    assert row_c2 is None


@pytest.mark.skipif(os.getenv("EDUNEXUS_DB_TESTS") != "1", reason=DB_TEST_REASON)
def test_t8_dashboard_read_creates_no_rows(client, db, student_user, educator_user):
    """T8 (Needs DB): Reading dashboard for class without activity returns zeros and creates zero rows."""
    c = Class(name="Class Gamma", subject="Physics", join_code=uuid.uuid4().hex[:8], educator_id=educator_user.id)
    db.add(c)
    db.commit()

    db.add(ClassEnrollment(class_id=c.id, student_id=student_user.id))
    db.commit()

    initial_count = db.query(Engagement).count()

    dash = progress_service.get_dashboard(db, str(student_user.id), str(c.id))
    assert dash["engagement"]["current_streak"] == 0
    assert dash["engagement"]["has_activity"] is False
    assert dash["engagement"]["is_inactive"] is False

    # Verifies read-only guarantee: zero rows created
    current_count = db.query(Engagement).count()
    assert current_count == initial_count
