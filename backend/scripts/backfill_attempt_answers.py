"""Backfill script for legacy quiz_attempt_answers and quiz_attempts points/options.

Finds completed quiz_attempt_answers rows where points_awarded, max_points,
or selected_options are NULL, evaluates the student's stored answer using
the official evaluate_question_answer scorer, and fills ONLY the NULL columns.

Usage:
  python backend/scripts/backfill_attempt_answers.py             # Dry run (default)
  python backend/scripts/backfill_attempt_answers.py --limit 50  # Dry run for first 50 attempts
  python backend/scripts/backfill_attempt_answers.py --apply     # Apply updates with batch commits
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# Ensure repo root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.core.database import SessionLocal
from backend.models.db import Quiz, QuizAttempt, QuizAttemptAnswer, QuizQuestion
from backend.services.quiz_service import evaluate_question_answer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill missing points_awarded, max_points, and selected_options on quiz_attempt_answers."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Apply changes to the database. Defaults to dry-run.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of qualifying attempts to process.",
    )
    return parser.parse_args()


def format_selected_options(chosen: object) -> str | None:
    if chosen is None:
        return None
    if isinstance(chosen, (list, tuple)):
        return json.dumps(chosen) if len(chosen) > 0 else None
    s = str(chosen)
    return s if s != "" else None


def main() -> None:
    args = parse_args()
    db = SessionLocal()

    print("=" * 60)
    print(f"Quiz Attempt Answers Backfill — Mode: {'APPLY' if args.apply else 'DRY RUN'}")
    print("=" * 60)

    try:
        # Find all completed attempts that have at least one answer row missing points or selected_options
        target_attempt_ids_query = (
            db.query(QuizAttemptAnswer.attempt_id)
            .join(QuizAttempt, QuizAttempt.id == QuizAttemptAnswer.attempt_id)
            .filter(
                QuizAttempt.completed.is_(True),
                (
                    QuizAttemptAnswer.points_awarded.is_(None)
                    | QuizAttemptAnswer.max_points.is_(None)
                    | QuizAttemptAnswer.selected_options.is_(None)
                ),
            )
            .distinct()
        )

        target_attempt_ids = [row[0] for row in target_attempt_ids_query.all()]
        total_target_attempts = len(target_attempt_ids)

        if args.limit is not None and args.limit > 0:
            target_attempt_ids = target_attempt_ids[: args.limit]

        print(
            f"Found {total_target_attempts} completed attempt(s) with missing answer fields. "
            f"Examining {len(target_attempt_ids)} attempt(s)."
        )

        attempts_examined = 0
        attempts_updated = 0
        answer_rows_updated = 0
        skipped_attempts = 0
        skip_reasons: dict[str, int] = defaultdict(int)

        batch_counter = 0

        for attempt_id in target_attempt_ids:
            attempts_examined += 1
            attempt = db.get(QuizAttempt, attempt_id)
            if not attempt:
                skipped_attempts += 1
                skip_reasons["attempt_not_found"] += 1
                continue

            quiz = db.get(Quiz, attempt.quiz_id)
            if not quiz:
                skipped_attempts += 1
                skip_reasons["quiz_not_found"] += 1
                continue

            # Skip if attempt version differs from quiz's current version
            if attempt.quiz_version != quiz.version:
                skipped_attempts += 1
                skip_reasons["version_mismatch"] += 1
                continue

            # Parse attempt answers JSON
            if not attempt.answers:
                skipped_attempts += 1
                skip_reasons["answers_json_empty"] += 1
                continue

            try:
                answers_map = json.loads(attempt.answers)
                if not isinstance(answers_map, dict):
                    skipped_attempts += 1
                    skip_reasons["answers_json_not_dict"] += 1
                    continue
            except Exception:
                skipped_attempts += 1
                skip_reasons["answers_json_parse_error"] += 1
                continue

            # Get all answer rows for this attempt
            answer_rows = (
                db.query(QuizAttemptAnswer)
                .filter(QuizAttemptAnswer.attempt_id == attempt.id)
                .all()
            )

            # Check if any question no longer exists
            question_map: dict[str, QuizQuestion] = {}
            missing_question = False
            for ans_row in answer_rows:
                q = db.get(QuizQuestion, ans_row.question_id)
                if not q:
                    missing_question = True
                    break
                question_map[str(ans_row.question_id)] = q

            if missing_question:
                skipped_attempts += 1
                skip_reasons["question_deleted"] += 1
                continue

            # Evaluate each answer row
            rows_modified_in_attempt = 0
            for ans_row in answer_rows:
                needs_update = (
                    ans_row.points_awarded is None
                    or ans_row.max_points is None
                    or ans_row.selected_options is None
                )
                if not needs_update:
                    continue

                q_id_str = str(ans_row.question_id)
                q = question_map[q_id_str]
                chosen = answers_map.get(q_id_str)

                max_p = float(q.points) if getattr(q, "points", None) is not None else 1.0
                _, credit_fraction = evaluate_question_answer(q, chosen)
                earned = max_p * credit_fraction
                selected_opt = format_selected_options(chosen)

                # Set ONLY the columns that are NULL
                if ans_row.points_awarded is None:
                    ans_row.points_awarded = earned
                if ans_row.max_points is None:
                    ans_row.max_points = max_p
                if ans_row.selected_options is None:
                    ans_row.selected_options = selected_opt

                rows_modified_in_attempt += 1

            if rows_modified_in_attempt > 0:
                answer_rows_updated += rows_modified_in_attempt
                attempts_updated += 1

            # Check attempt-level points_earned and max_points
            all_answers_complete = all(
                r.points_awarded is not None and r.max_points is not None
                for r in answer_rows
            )
            if all_answers_complete and (attempt.points_earned is None or attempt.max_points is None):
                if attempt.points_earned is None:
                    attempt.points_earned = sum(r.points_awarded for r in answer_rows)  # type: ignore[misc]
                if attempt.max_points is None:
                    attempt.max_points = sum(r.max_points for r in answer_rows)  # type: ignore[misc]

            batch_counter += 1
            if args.apply and batch_counter >= 200:
                db.commit()
                batch_counter = 0

        if args.apply:
            db.commit()
            print("Successfully committed all changes.")

        print("\n--- Backfill Summary ---")
        print(f"Attempts examined:         {attempts_examined}")
        print(f"Attempts updated:          {attempts_updated}")
        print(f"Answer rows updated:       {answer_rows_updated}")
        print(f"Attempts skipped:          {skipped_attempts}")
        if skip_reasons:
            print("Skip breakdown:")
            for reason, cnt in sorted(skip_reasons.items()):
                print(f"  - {reason}: {cnt}")
        print("-" * 24)

    finally:
        db.close()


if __name__ == "__main__":
    main()
