"""
Generic background jobs on PostgreSQL (same pattern as the email outbox).

    enqueue(db, "ai.triage", {"ticket_id": 42}, tenant_id=1)   # inside the business transaction
    run_due_jobs()                                             # worker loop

* Transactional enqueue: a job exists if and only if the change that caused it
  committed — no AI triage for a ticket creation that rolled back.
* Claiming uses FOR UPDATE SKIP LOCKED, one job per transaction, so any number
  of workers run concurrently without double-processing.
* Failures retry with exponential backoff; after `max_attempts` the job is
  parked as `dead` with its last error (dead letter) and an audit-visible log.
* `dedupe_key` makes enqueueing idempotent for jobs that must not run twice
  concurrently for the same subject (e.g. one pending triage per ticket).
* Handlers must be idempotent: a crash after the work but before the commit
  means the job runs again.
"""

import logging
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core import metrics
from app.db.database import SessionLocal, utcnow
from app.db.models import Job

logger = logging.getLogger(__name__)

Handler = Callable[[Session, dict[str, Any]], dict[str, Any] | None]
HANDLERS: dict[str, Handler] = {}
# A running job whose worker vanished is reclaimed after this long.
LEASE = timedelta(minutes=10)


def handler(kind: str):
    def register(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn

    return register


def enqueue(
    db: Session,
    kind: str,
    payload: dict[str, Any],
    *,
    tenant_id: int | None = None,
    dedupe_key: str | None = None,
    max_attempts: int = 5,
    delay_seconds: float = 0,
) -> Job | None:
    if dedupe_key is not None:
        existing = (
            db.query(Job).filter(Job.dedupe_key == dedupe_key, Job.status.in_(["queued", "running", "failed"])).first()
        )
        if existing is not None:
            return None
    job = Job(
        kind=kind,
        payload=payload,
        tenant_id=tenant_id,
        dedupe_key=dedupe_key,
        max_attempts=max_attempts,
        run_after=utcnow() + timedelta(seconds=delay_seconds),
    )
    db.add(job)
    return job


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(15 * 2 ** max(attempts - 1, 0), 3600))


def _claim(db: Session) -> Job | None:
    """Claim one due job in its own committed transaction. A job left `running`
    by a crashed worker becomes claimable again once its lease expires."""
    now = utcnow()
    job = (
        db.query(Job)
        .filter(
            or_(
                (Job.status.in_(["queued", "failed"])) & (Job.run_after <= now),
                (Job.status == "running") & (Job.started_at < now - LEASE),
            )
        )
        .order_by(Job.run_after, Job.id)
        .with_for_update(skip_locked=True)
        .first()
    )
    if job is None:
        db.rollback()
        return None
    job.status, job.started_at, job.attempts = "running", now, job.attempts + 1
    db.commit()
    return job


def _load_handlers() -> None:
    # Handler modules register themselves on import; loading them here keeps
    # every entry point (inline API loop, worker, tests) consistent.
    import app.ai.jobs  # noqa: F401
    import app.kb.ingest  # noqa: F401


def run_due_jobs(session_factory=SessionLocal, limit: int = 20) -> int:
    _load_handlers()
    processed = 0
    for _ in range(limit):
        db = session_factory()
        try:
            job = _claim(db)
            if job is None:
                break
            job_id, kind, payload = job.id, job.kind, dict(job.payload or {})
            fn = HANDLERS.get(kind)
            started = time.perf_counter()
            try:
                if fn is None:
                    raise LookupError(f"no handler registered for job kind {kind!r}")
                result = fn(db, payload)
                job = db.get(Job, job_id)
                # The handler's work and the "done" marker commit together.
                job.status, job.result, job.last_error, job.finished_at = "done", result, None, utcnow()
                job.duration_ms = round((time.perf_counter() - started) * 1000, 1)
                db.commit()
                metrics.JOBS.labels(kind, "done").inc()
                metrics.JOB_DURATION.labels(kind).observe(time.perf_counter() - started)
            except Exception as exc:  # recorded, retried, never raised to the loop
                db.rollback()
                job = db.get(Job, job_id)
                job.last_error = f"{type(exc).__name__}: {exc}"[:2000]
                job.duration_ms = round((time.perf_counter() - started) * 1000, 1)
                if job.attempts >= job.max_attempts:
                    job.status, job.finished_at = "dead", utcnow()
                    logger.error("job_dead_lettered", extra={"job_id": job_id, "kind": kind})
                else:
                    job.status, job.run_after = "failed", utcnow() + _backoff(job.attempts)
                    logger.warning("job_failed", extra={"job_id": job_id, "kind": kind, "attempts": job.attempts})
                db.commit()
                metrics.JOBS.labels(kind, job.status).inc()
            processed += 1
        except Exception:
            db.rollback()
            logger.exception("job_loop_failed")
            break
        finally:
            db.close()
    return processed
