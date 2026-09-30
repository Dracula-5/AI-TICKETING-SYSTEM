"""
Background worker:  python -m app.worker   (health check: python -m app.worker --check)

Runs the periodic jobs that must not live inside request handling:

* SLA sweep — breach recording, escalation, auto-close (services/sla.py)
* email delivery — drains the transactional outbox with retry/dead-letter
  (services/email.py)
* background jobs — AI triage and other queued work (services/jobs.py)

Every job is idempotent and claims rows with FOR UPDATE SKIP LOCKED, so
running several worker replicas is safe (no leader election needed). The loop
writes a heartbeat file each tick; the container health check fails if it goes
stale, which catches a hung worker, not just a dead one.
"""

import logging
import signal
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.monitoring import init_error_monitoring
from app.db.database import SessionLocal
from app.services.email import deliver_pending
from app.services.jobs import run_due_jobs
from app.services.sla import run_sla_sweep

logger = logging.getLogger("app.worker")

HEARTBEAT_FILE = Path("/tmp/nexadesk-worker.heartbeat")  # noqa: S108  # nosec B108 -- container-local liveness marker
HEARTBEAT_MAX_AGE_SECONDS = 120


@dataclass
class PeriodicJob:
    name: str
    interval_seconds: float
    run: Callable[[], object]
    next_run: float = 0.0

    def run_if_due(self, now: float) -> None:
        if now < self.next_run:
            return
        self.next_run = now + self.interval_seconds
        started = time.perf_counter()
        try:
            result = self.run()
            logger.debug("job_done", extra={"job": self.name, "result": result})
        except Exception:
            logger.exception("job_failed", extra={"job": self.name})
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            if duration_ms > self.interval_seconds * 1000:
                logger.warning("job_overran_interval", extra={"job": self.name, "duration_ms": duration_ms})


def _sla_sweep() -> dict:
    db = SessionLocal()
    try:
        return run_sla_sweep(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _ai_monitoring() -> dict:
    """Daily drift / agreement check for every organization with AI enabled."""
    from app.ai import monitoring
    from app.db.models import Tenant

    db = SessionLocal()
    try:
        results = {}
        for tenant in db.query(Tenant).all():
            results[tenant.id] = monitoring.run(db, tenant).status
        db.commit()
        return results
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def build_jobs() -> list[PeriodicJob]:
    return [
        PeriodicJob("sla_sweep", settings.sla_sweep_interval_seconds, _sla_sweep),
        PeriodicJob("email_delivery", settings.email_poll_interval_seconds, deliver_pending),
        PeriodicJob("jobs", settings.job_poll_interval_seconds, run_due_jobs),
        PeriodicJob("ai_monitoring", 24 * 3600, _ai_monitoring),
    ]


def run(stop: threading.Event, jobs: list[PeriodicJob] | None = None, tick_seconds: float = 1.0) -> None:
    jobs = jobs if jobs is not None else build_jobs()
    logger.info("worker_started", extra={"jobs": [j.name for j in jobs], "environment": settings.environment})
    while not stop.is_set():
        now = time.monotonic()
        for job in jobs:
            job.run_if_due(now)
        HEARTBEAT_FILE.touch()
        stop.wait(tick_seconds)
    logger.info("worker_stopped")


def healthy() -> bool:
    try:
        return time.time() - HEARTBEAT_FILE.stat().st_mtime < HEARTBEAT_MAX_AGE_SECONDS
    except FileNotFoundError:
        return False


def main() -> None:
    if "--check" in sys.argv:
        sys.exit(0 if healthy() else 1)
    setup_logging()
    settings.validate_for_environment()
    init_error_monitoring("worker")
    if settings.worker_metrics_port:
        from app.core import metrics

        metrics.serve_worker_metrics(settings.worker_metrics_port)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    run(stop)


if __name__ == "__main__":
    main()
