from __future__ import annotations

import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from backend.core.config import get_settings
from backend.core.database import SessionLocal
from backend.pipeline.embedder import get_embedding_model
from backend.services.ingestion_jobs import drain_once, sweep_stale

settings = get_settings()


def run_once(embedding_model) -> None:
    db = SessionLocal()
    try:
        swept = sweep_stale(db)
    finally:
        db.close()
    if swept:
        print(f"[WORKER] Swept {swept} stale job(s).")

    drained = 0
    while drain_once(SessionLocal, embedding_model):
        drained += 1
    if drained:
        print(f"[WORKER] Drained {drained} job(s).")


def run_forever(embedding_model) -> None:
    print(
        f"[WORKER] Ready. Polling ingestion_jobs every "
        f"{settings.ingestion_poll_interval_seconds}s."
    )
    while True:
        run_once(embedding_model)
        time.sleep(settings.ingestion_poll_interval_seconds)


if __name__ == "__main__":
    print("[WORKER] Loading embedding model...")
    model = get_embedding_model()

    if "--once" in sys.argv:
        run_once(model)
    else:
        try:
            run_forever(model)
        except KeyboardInterrupt:
            print("[WORKER] Shutting down.")
