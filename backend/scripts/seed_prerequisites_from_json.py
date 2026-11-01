"""Idempotent script to seed prerequisite maps from data JSON files into the DB topic graph.

Usage:
    python backend/scripts/seed_prerequisites_from_json.py --dry-run
    python backend/scripts/seed_prerequisites_from_json.py --subject "Operating Systems" --dry-run
    python backend/scripts/seed_prerequisites_from_json.py --apply (REQUIRES confirmation)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.database import SessionLocal
from backend.models.db import PrerequisiteMap, Subject

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def seed_prerequisites(db: Session, subject_filter: str | None = None, dry_run: bool = True) -> dict[str, Any]:
    json_files = list(DATA_DIR.glob("prerequisites_*.json"))
    stats: dict[str, Any] = {
        "files_scanned": len(json_files),
        "topics_found": 0,
        "topics_to_insert": 0,
        "topics_to_update": 0,
        "subjects_matched": [],
        "dry_run": dry_run,
    }

    for json_file in json_files:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            print(f"[SEED ERROR] Failed to read {json_file.name}: {exc}")
            continue

        subject_name = data.get("subject", "").strip()
        prereq_map = data.get("prerequisite_map", {})
        if not subject_name or not prereq_map:
            continue

        if subject_filter and subject_filter.lower() not in subject_name.lower():
            continue

        subject_row = (
            db.query(Subject)
            .filter(func.lower(Subject.name) == subject_name.lower())
            .first()
        )
        if subject_row is None:
            print(f"[SEED SKIP] Subject '{subject_name}' not found in database.")
            continue

        stats["subjects_matched"].append(subject_name)
        existing_rows = {
            r.topic: r
            for r in db.query(PrerequisiteMap).filter(PrerequisiteMap.subject_id == subject_row.id).all()
        }

        for topic, requires in prereq_map.items():
            stats["topics_found"] += 1
            topic_str = str(topic).strip()
            req_list = list(requires) if isinstance(requires, list) else []

            if topic_str in existing_rows:
                stats["topics_to_update"] += 1
                if not dry_run:
                    row = existing_rows[topic_str]
                    row.requires = req_list
            else:
                stats["topics_to_insert"] += 1
                if not dry_run:
                    new_row = PrerequisiteMap(
                        subject_id=subject_row.id,
                        subject=subject_row.name,
                        topic=topic_str,
                        requires=req_list,
                        related_concepts=[],
                    )
                    db.add(new_row)

    if not dry_run:
        db.commit()
        print("[SEED] Changes committed successfully.")
    else:
        print(f"[SEED DRY-RUN] Would insert {stats['topics_to_insert']}, would update {stats['topics_to_update']}")

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed topic graph from JSON data files.")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Preview actions without writing")
    parser.add_argument("--apply", action="store_true", default=False, help="Execute and commit changes")
    parser.add_argument("--subject", type=str, default=None, help="Filter to a specific subject name")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        print("Safety check: must pass either --dry-run or --apply. Defaulting to --dry-run.")
        is_dry_run = True
    else:
        is_dry_run = not args.apply

    db = SessionLocal()
    try:
        results = seed_prerequisites(db, subject_filter=args.subject, dry_run=is_dry_run)
        print(f"Summary: {results}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
