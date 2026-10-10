import logging
import threading
from typing import Any

from backend.core.database import SessionLocal
from backend.services import ingestion_jobs

logger = logging.getLogger(__name__)


class IngestionRunner:
    def __init__(self, embedding_model: Any, poll_interval_seconds: float):
        self._model = embedding_model
        self._interval = poll_interval_seconds
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="ingestion-runner", daemon=True)
        self._thread.start()
        print(f"[INGESTION RUNNER] Started (stale sweep every {self._interval:.0f}s, uploads wake it immediately)")

    def wake(self) -> None:
        self._wake.set()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        print("[INGESTION RUNNER] Stopped")

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._run_cycle()
            except Exception:  # noqa: BLE001
                logger.exception("Ingestion runner cycle failed")
            self._wake.wait(timeout=self._interval)
            self._wake.clear()

    def _run_cycle(self) -> None:
        db = SessionLocal()
        try:
            ingestion_jobs.sweep_stale(db)
        finally:
            db.close()
        while not self._stop.is_set() and ingestion_jobs.drain_once(SessionLocal, self._model):
            pass


_runner: IngestionRunner | None = None


def start_runner(embedding_model: Any, poll_interval_seconds: float) -> IngestionRunner:
    global _runner
    if _runner is None:
        _runner = IngestionRunner(embedding_model, poll_interval_seconds)
        _runner.start()
    return _runner


def stop_runner() -> None:
    global _runner
    if _runner is not None:
        _runner.stop()
        _runner = None


def notify_new_job() -> None:
    if _runner is not None:
        _runner.wake()
