"""Mastery Version Comparison Script (v1 vs v2)

Runs pure synthetic scenarios comparing:
  - v1 heuristic: per-quiz ratios with static weighted recency window
  - v2 heuristic: per-question evidence with exponential decay, guessing penalty, and credible interval

NOTE: Every output row is a synthetic demonstration only, not evidence of real-world performance.
"""
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

# Ensure repo root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.services.mastery_v2 import AttemptEvidence, compute_mastery
from backend.services.progress_service import calculate_mastery, calculate_trend

DISCLAIMER = "synthetic demonstration only, not evidence of real-world performance"


@dataclass
class SyntheticQuiz:
    session_id: str
    timestamp: datetime
    answers: List[bool]  # True = correct, False = incorrect
    option_count: int = 4


@dataclass
class Scenario:
    name: str
    description: str
    quizzes: List[SyntheticQuiz]


def build_scenarios(now: datetime) -> List[Scenario]:
    return [
        Scenario(
            name="New learner",
            description="No attempts made yet",
            quizzes=[],
        ),
        Scenario(
            name="One correct",
            description="Single 1-question quiz answered correctly (demonstrates v1 overconfidence)",
            quizzes=[
                SyntheticQuiz("s1", now - timedelta(hours=2), [True]),
            ],
        ),
        Scenario(
            name="One wrong",
            description="Single 1-question quiz answered incorrectly",
            quizzes=[
                SyntheticQuiz("s1", now - timedelta(hours=2), [False]),
            ],
        ),
        Scenario(
            name="Many correct",
            description="4 quizzes of 4 questions each (100% correct across distinct sessions)",
            quizzes=[
                SyntheticQuiz(f"s{i}", now - timedelta(days=4 - i), [True, True, True, True])
                for i in range(1, 5)
            ],
        ),
        Scenario(
            name="Mixed performance",
            description="5 quizzes with alternating 50% and 75% accuracy",
            quizzes=[
                SyntheticQuiz("s1", now - timedelta(days=6), [True, False, True, False]),
                SyntheticQuiz("s2", now - timedelta(days=5), [True, True, True, False]),
                SyntheticQuiz("s3", now - timedelta(days=4), [False, True, True, False]),
                SyntheticQuiz("s4", now - timedelta(days=2), [True, True, False, True]),
                SyntheticQuiz("s5", now - timedelta(hours=5), [True, True, True, False]),
            ],
        ),
        Scenario(
            name="Improving learner",
            description="Early quizzes 0-25% correct, recent quizzes 100% correct",
            quizzes=[
                SyntheticQuiz("s1", now - timedelta(days=8), [False, False, False, False]),
                SyntheticQuiz("s2", now - timedelta(days=6), [True, False, False, False]),
                SyntheticQuiz("s3", now - timedelta(days=3), [True, True, True, True]),
                SyntheticQuiz("s4", now - timedelta(hours=10), [True, True, True, True]),
            ],
        ),
        Scenario(
            name="Declining learner",
            description="Early quizzes 100% correct, recent quizzes 0-25% correct",
            quizzes=[
                SyntheticQuiz("s1", now - timedelta(days=8), [True, True, True, True]),
                SyntheticQuiz("s2", now - timedelta(days=6), [True, True, True, True]),
                SyntheticQuiz("s3", now - timedelta(days=3), [True, False, False, False]),
                SyntheticQuiz("s4", now - timedelta(hours=10), [False, False, False, False]),
            ],
        ),
        Scenario(
            name="Stale evidence",
            description="4 quizzes of 4 questions, 100% correct, but completed 90 days ago",
            quizzes=[
                SyntheticQuiz(f"s{i}", now - timedelta(days=94 - i), [True, True, True, True])
                for i in range(1, 5)
            ],
        ),
        Scenario(
            name="Random guessing",
            description="8 quizzes of 4 questions with ~25% correct (1 out of 4 on each)",
            quizzes=[
                SyntheticQuiz(f"s{i}", now - timedelta(days=8 - i), [True, False, False, False])
                for i in range(1, 9)
            ],
        ),
    ]


def run_comparison():
    now = datetime(2026, 10, 29, 12, 0, 0, tzinfo=timezone.utc)
    scenarios = build_scenarios(now)

    print("=" * 115)
    print("EDUNEXUS AI -- MASTERY ESTIMATE COMPARISON (v1 vs v2)")
    print(f"NOTE: {DISCLAIMER}")
    print("=" * 115)
    print(
        f"{'Scenario':<20} | {'Attempts':<10} | {'v1 Score':<9} | {'v1 Trend':<11} | "
        f"{'v2 Est.':<8} | {'v2 Band':<8} | {'v2 Evidence':<12} | {'90% CI':<13} | {'v2 Trend':<10}"
    )
    print("-" * 115)

    for sc in scenarios:
        # Calculate v1: list of quiz score ratios, most recent first
        if sc.quizzes:
            v1_scores_most_recent_first = [
                sum(1 for a in q.answers if a) / len(q.answers) for q in reversed(sc.quizzes)
            ]
            v1_score = calculate_mastery(v1_scores_most_recent_first)
            v1_trend = calculate_trend(v1_scores_most_recent_first).value
            v1_score_str = f"{v1_score:.3f}"
        else:
            v1_score_str = "0.000"
            v1_trend = "not_started"

        # Calculate v2: flat list of AttemptEvidence objects
        evidence_list: List[AttemptEvidence] = []
        q_idx = 0
        for quiz in sc.quizzes:
            for ans in quiz.answers:
                q_idx += 1
                evidence_list.append(
                    AttemptEvidence(
                        question_id=f"q_{q_idx}",
                        session_id=quiz.session_id,
                        correct=ans,
                        timestamp=quiz.timestamp,
                        option_count=quiz.option_count,
                        difficulty=None,
                    )
                )

        v2_res = compute_mastery(evidence_list, now=now)
        v2_est_str = f"{v2_res.mastery_estimate:.3f}" if v2_res.mastery_estimate is not None else "None"
        ci_str = (
            f"[{v2_res.ci_low:.2f}, {v2_res.ci_high:.2f}]"
            if v2_res.ci_low is not None and v2_res.ci_high is not None
            else "None"
        )
        total_q = sum(len(q.answers) for q in sc.quizzes)
        attempts_summary = f"{len(sc.quizzes)}q / {total_q}a"

        print(
            f"{sc.name:<20} | {attempts_summary:<10} | {v1_score_str:<9} | {v1_trend:<11} | "
            f"{v2_est_str:<8} | {v2_res.mastery_band:<8} | {v2_res.evidence_state:<12} | {ci_str:<13} | {v2_res.trend:<10}"
        )
        print(f"   -> [{DISCLAIMER}] - {sc.description}")

    print("=" * 115)


if __name__ == "__main__":
    run_comparison()
