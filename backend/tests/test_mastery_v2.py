from datetime import datetime, timedelta, timezone
import pytest

from backend.services.mastery_v2 import (
    AttemptEvidence,
    MasteryConfig,
    compute_mastery,
    normalize_topic_key,
    result_to_dict,
)


@pytest.fixture
def fixed_now():
    return datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_empty_attempts(fixed_now):
    res = compute_mastery([], now=fixed_now)
    assert res.mastery_estimate is None
    assert res.mastery_band == "unknown"
    assert res.evidence_state == "none"
    assert res.effective_attempts == 0.0
    assert res.distinct_questions == 0
    assert res.distinct_sessions == 0
    assert res.ci_low is None
    assert res.ci_high is None
    assert res.trend == "unknown"
    assert res.last_evidence_at is None

    # Also None input
    res_none = compute_mastery(None, now=fixed_now)
    assert res_none.evidence_state == "none"

    d = result_to_dict(res)
    assert d["version"] == "v2.0"
    assert d["mastery_estimate"] is None
    assert d["last_evidence_at"] is None


def test_one_correct_answer(fixed_now):
    attempts = [
        AttemptEvidence(
            question_id="q1",
            session_id="s1",
            correct=True,
            timestamp=fixed_now,
            option_count=4,
        )
    ]
    res = compute_mastery(attempts, now=fixed_now)
    assert res.evidence_state == "insufficient"
    assert res.mastery_estimate is not None
    assert res.mastery_estimate < 1.0
    assert res.mastery_estimate > 0.0
    assert res.distinct_questions == 1
    assert res.distinct_sessions == 1


def test_six_correct_answers_sufficient_high(fixed_now):
    attempts = [
        AttemptEvidence(
            question_id=f"q{i}",
            session_id=f"s{i % 2}",  # across 2 distinct sessions s0 and s1
            correct=True,
            timestamp=fixed_now - timedelta(hours=i),
            option_count=4,
        )
        for i in range(6)
    ]
    res = compute_mastery(attempts, now=fixed_now)
    assert res.evidence_state == "sufficient"
    assert res.mastery_band == "high"
    assert res.mastery_estimate is not None
    assert res.mastery_estimate >= 0.75
    assert res.distinct_questions == 6
    assert res.distinct_sessions == 2


def test_many_wrong_answers_low(fixed_now):
    attempts = [
        AttemptEvidence(
            question_id=f"q{i}",
            session_id=f"s{i % 3}",
            correct=False,
            timestamp=fixed_now - timedelta(hours=i),
            option_count=4,
        )
        for i in range(8)
    ]
    res = compute_mastery(attempts, now=fixed_now)
    assert res.evidence_state == "sufficient"
    assert res.mastery_band == "low"
    assert res.mastery_estimate is not None
    assert res.mastery_estimate < 0.40


def test_random_guess_pattern(fixed_now):
    # 40 attempts: 10 correct, 30 wrong (~25% correct on 4-option MCQ)
    attempts = []
    for i in range(40):
        attempts.append(
            AttemptEvidence(
                question_id=f"q{i % 10}",
                session_id=f"s{i % 5}",
                correct=(i % 4 == 0),  # 25% correct
                timestamp=fixed_now - timedelta(hours=40 - i),
                option_count=4,
            )
        )
    res = compute_mastery(attempts, now=fixed_now)
    assert res.evidence_state == "sufficient"
    assert res.mastery_estimate is not None
    assert res.mastery_estimate < 0.15


def test_single_session_insufficient_evidence(fixed_now):
    # 5 correct answers, distinct questions, but all in ONE session
    attempts = [
        AttemptEvidence(
            question_id=f"q{i}",
            session_id="only_session_1",
            correct=True,
            timestamp=fixed_now - timedelta(minutes=5 * i),
            option_count=4,
        )
        for i in range(5)
    ]
    res = compute_mastery(attempts, now=fixed_now)
    assert res.distinct_questions == 5
    assert res.distinct_sessions == 1
    assert res.evidence_state == "insufficient"


def test_stale_evidence_decay(fixed_now):
    # 6 attempts, but 90 days ago
    stale_time = fixed_now - timedelta(days=90)
    attempts = [
        AttemptEvidence(
            question_id=f"q{i}",
            session_id=f"s{i % 2}",
            correct=True,
            timestamp=stale_time + timedelta(hours=i),
            option_count=4,
        )
        for i in range(6)
    ]
    res = compute_mastery(attempts, now=fixed_now)
    # 90 days with 14-day half-life decays weight by ~2^6.4 -> factor of ~0.012
    # 6 * 0.012 ≈ 0.07 << min_effective_attempts (3.0)
    assert res.effective_attempts < 1.0
    assert res.evidence_state == "insufficient"


def test_trend_improving_declining_flat(fixed_now):
    # 7 attempts across 2 sessions (min 3 attempts needed, recent_window=3, earlier=4)
    # Improving: earlier 4 all wrong, recent 3 all correct
    improving_attempts = [
        AttemptEvidence(
            question_id=f"q{i}",
            session_id=f"s{i % 2}",
            correct=False,
            timestamp=fixed_now - timedelta(days=7 - i),
            option_count=4,
        )
        for i in range(4)
    ] + [
        AttemptEvidence(
            question_id=f"q{i}",
            session_id=f"s{i % 2}",
            correct=True,
            timestamp=fixed_now - timedelta(days=3 - (i - 4)),
            option_count=4,
        )
        for i in range(4, 7)
    ]
    res_imp = compute_mastery(improving_attempts, now=fixed_now)
    assert res_imp.evidence_state == "sufficient"
    assert res_imp.trend == "improving"

    # Declining: earlier 4 all correct, recent 3 all wrong
    declining_attempts = [
        AttemptEvidence(
            question_id=f"q{i}",
            session_id=f"s{i % 2}",
            correct=True,
            timestamp=fixed_now - timedelta(days=7 - i),
            option_count=4,
        )
        for i in range(4)
    ] + [
        AttemptEvidence(
            question_id=f"q{i}",
            session_id=f"s{i % 2}",
            correct=False,
            timestamp=fixed_now - timedelta(days=3 - (i - 4)),
            option_count=4,
        )
        for i in range(4, 7)
    ]
    res_dec = compute_mastery(declining_attempts, now=fixed_now)
    assert res_dec.evidence_state == "sufficient"
    assert res_dec.trend == "declining"

    # Flat: earlier 6 attempts (3 correct, 3 wrong -> 0.5), recent 4 attempts (2 correct, 2 wrong -> 0.5)
    flat_attempts = [
        AttemptEvidence(
            question_id=f"q{i}",
            session_id=f"s{i % 2}",
            correct=(i % 2 == 0),
            timestamp=fixed_now - timedelta(days=10 - i),
            option_count=4,
        )
        for i in range(10)
    ]
    res_flat = compute_mastery(flat_attempts, now=fixed_now, cfg=MasteryConfig(recent_window=4))
    assert res_flat.evidence_state == "sufficient"
    assert res_flat.trend == "flat"


def test_invalid_and_edge_inputs(fixed_now):
    # None items in list, naive datetime, future timestamp
    naive_dt = datetime(2026, 5, 20, 10, 0, 0)  # no tzinfo
    future_dt = fixed_now + timedelta(days=5)

    attempts = [
        None,
        AttemptEvidence(
            question_id="q1",
            session_id="s1",
            correct=True,
            timestamp=naive_dt,
            option_count=4,
        ),
        None,
        AttemptEvidence(
            question_id="q2",
            session_id="s2",
            correct=False,
            timestamp=future_dt,
            option_count=4,
        ),
    ]
    res = compute_mastery(attempts, now=fixed_now)
    assert res.distinct_questions == 2
    assert res.distinct_sessions == 2
    assert res.mastery_estimate is not None


def test_credible_interval_bounds(fixed_now):
    # Verify ci_low <= estimate <= ci_high and within [0, 1] across several random mixes
    for correct_count in (1, 3, 5, 8):
        attempts = [
            AttemptEvidence(
                question_id=f"q{i}",
                session_id=f"s{i % 2}",
                correct=(i < correct_count),
                timestamp=fixed_now - timedelta(hours=i),
                option_count=4,
            )
            for i in range(10)
        ]
        res = compute_mastery(attempts, now=fixed_now)
        assert res.mastery_estimate is not None
        assert res.ci_low is not None
        assert res.ci_high is not None
        assert 0.0 <= res.ci_low <= res.mastery_estimate <= res.ci_high <= 1.0


def test_normalize_topic_key():
    # Casefolding
    assert normalize_topic_key("CPU Scheduling") == "cpu scheduling"
    assert normalize_topic_key("Operating Systems") == "operating systems"

    # Extra spaces / tabs / newlines
    assert normalize_topic_key("  Virtual   Memory \n\t Management  ") == "virtual memory management"

    # None and empty
    assert normalize_topic_key(None) is None
    assert normalize_topic_key("") is None
    assert normalize_topic_key("   ") is None
    assert normalize_topic_key("\n\t") is None
