from __future__ import annotations

import signal
import sys
import threading

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from backend.core.config import get_settings
from backend.core.database import SessionLocal
from backend.pipeline.embedder import get_embedding_model
from backend.services.ingestion_jobs import drain_once, sweep_stale

settings = get_settings()
stop_requested = threading.Event()


def _request_stop(signum, _frame) -> None:
    print(f"[WORKER] Received signal {signum}; finishing the current job before exiting.")
    stop_requested.set()


def run_once(embedding_model) -> None:
    db = SessionLocal()
    try:
        swept = sweep_stale(db)
    finally:
        db.close()
    if swept:
        print(f"[WORKER] Swept {swept} stale job(s).")

    drained = 0
    while not stop_requested.is_set() and drain_once(SessionLocal, embedding_model):
        drained += 1
    if drained:
        print(f"[WORKER] Drained {drained} job(s).")


def run_forever(embedding_model) -> None:
    print(f"[WORKER] Ready. Polling ingestion_jobs every {settings.ingestion_poll_interval_seconds}s.")
    while not stop_requested.is_set():
        run_once(embedding_model)
        stop_requested.wait(settings.ingestion_poll_interval_seconds)
    print("[WORKER] Stopped cleanly.")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    print("[WORKER] Loading embedding model...")
    model = get_embedding_model()

    if "--once" in sys.argv:
        run_once(model)
    else:
        run_forever(model)
