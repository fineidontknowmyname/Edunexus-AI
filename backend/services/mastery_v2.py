from dataclasses import dataclass
from datetime import datetime, timezone
import math


def normalize_topic_key(topic: str | None) -> str | None:
    if topic is None:
        return None
    key = " ".join(str(topic).split()).casefold()
    return key or None


@dataclass(frozen=True)
class AttemptEvidence:
    question_id: str
    session_id: str                    # the quiz attempt id
    correct: bool
    timestamp: datetime
    option_count: int | None = None    # MCQ option count, else None
    difficulty: float | None = None    # keep None in Phase 1


@dataclass(frozen=True)
class MasteryConfig:
    half_life_days: float = 14.0
    prior_a: float = 1.0
    prior_b: float = 1.0
    min_effective_attempts: float = 3.0
    min_distinct_questions: int = 2
    min_distinct_sessions: int = 2
    low_threshold: float = 0.4
    high_threshold: float = 0.75
    max_attempts: int = 50
    recent_window: int = 3
    trend_delta: float = 0.15
    ci_z: float = 1.645                # about a 90% interval


@dataclass(frozen=True)
class MasteryResult:
    mastery_estimate: float | None
    mastery_band: str          # low | medium | high | unknown
    evidence_state: str        # none | insufficient | sufficient
    effective_attempts: float
    distinct_questions: int
    distinct_sessions: int
    ci_low: float | None
    ci_high: float | None
    trend: str                 # improving | flat | declining | unknown
    last_evidence_at: datetime | None


def _utc(ts: datetime) -> datetime:
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def compute_mastery(
    attempts: list[AttemptEvidence] | None,
    now: datetime | None = None,
    cfg: MasteryConfig = MasteryConfig(),
) -> MasteryResult:
    now = _utc(now or datetime.now(timezone.utc))
    valid = [
        a for a in (attempts or [])
        if a is not None and a.correct is not None and a.timestamp is not None
    ]
    valid.sort(key=lambda a: _utc(a.timestamp))
    valid = valid[-cfg.max_attempts:]
    if not valid:
        return MasteryResult(
            mastery_estimate=None,
            mastery_band="unknown",
            evidence_state="none",
            effective_attempts=0.0,
            distinct_questions=0,
            distinct_sessions=0,
            ci_low=None,
            ci_high=None,
            trend="unknown",
            last_evidence_at=None,
        )

    sum_w = sum_wc = sum_wg = 0.0
    for a in valid:
        age_days = max(0.0, (now - _utc(a.timestamp)).total_seconds() / 86400)
        w = 0.5 ** (age_days / cfg.half_life_days)
        if a.difficulty is not None and a.difficulty > 0:
            w *= a.difficulty
        guess = (
            1.0 / a.option_count
            if a.option_count and a.option_count >= 2 else 0.0
        )
        sum_w += w
        sum_wc += w * (1.0 if a.correct else 0.0)
        sum_wg += w * guess

    g = sum_wg / sum_w if sum_w > 0 else 0.0
    alpha = cfg.prior_a + sum_wc
    beta = cfg.prior_b + (sum_w - sum_wc)
    p = alpha / (alpha + beta)
    var = (alpha * beta) / (((alpha + beta) ** 2) * (alpha + beta + 1))
    sd = math.sqrt(var)

    def adj(x: float) -> float:  # remove the expected guessing rate
        return _clip((x - g) / (1.0 - g)) if g < 1.0 else 0.0

    estimate = adj(p)
    ci_low, ci_high = adj(p - cfg.ci_z * sd), adj(p + cfg.ci_z * sd)

    distinct_q = len({a.question_id for a in valid})
    distinct_s = len({a.session_id for a in valid})
    if (
        sum_w < cfg.min_effective_attempts
        or distinct_q < cfg.min_distinct_questions
        or distinct_s < cfg.min_distinct_sessions
    ):
        evidence = "insufficient"
    else:
        evidence = "sufficient"

    if estimate < cfg.low_threshold:
        band = "low"
    elif estimate >= cfg.high_threshold:
        band = "high"
    else:
        band = "medium"

    trend = "unknown"
    if evidence == "sufficient" and len(valid) > cfg.recent_window:
        recent = valid[-cfg.recent_window:]
        earlier = valid[:-cfg.recent_window]
        r = sum(1 for a in recent if a.correct) / len(recent)
        e = sum(1 for a in earlier if a.correct) / len(earlier)
        if r - e > cfg.trend_delta:
            trend = "improving"
        elif e - r > cfg.trend_delta:
            trend = "declining"
        else:
            trend = "flat"

    return MasteryResult(
        mastery_estimate=estimate,
        mastery_band=band,
        evidence_state=evidence,
        effective_attempts=sum_w,
        distinct_questions=distinct_q,
        distinct_sessions=distinct_s,
        ci_low=ci_low,
        ci_high=ci_high,
        trend=trend,
        last_evidence_at=_utc(valid[-1].timestamp),
    )


def result_to_dict(r: MasteryResult) -> dict:
    return {
        "mastery_estimate": r.mastery_estimate,
        "mastery_band": r.mastery_band,
        "evidence_state": r.evidence_state,
        "effective_attempts": r.effective_attempts,
        "distinct_questions": r.distinct_questions,
        "distinct_sessions": r.distinct_sessions,
        "ci_low": r.ci_low,
        "ci_high": r.ci_high,
        "trend": r.trend,
        "last_evidence_at": r.last_evidence_at.isoformat() if r.last_evidence_at else None,
        "version": "v2.0",
    }
