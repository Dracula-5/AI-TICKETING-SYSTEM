"""
Prometheus metrics (P12).

Counters/histograms are updated where things happen (request middleware, job
runner, agent, LLM ledger, KB queries). Queue and backlog gauges are read from
the database at scrape time, so they are always the truth, never a cached
number. With several API processes (uvicorn --workers N) set
PROMETHEUS_MULTIPROC_DIR (the container entrypoint does) and every process
writes to shared files that one scrape aggregates.

Exposed at GET /metrics on the backend and on the worker's metrics port —
both only on the internal network (Caddy routes nothing to them).
"""

import os
import time

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import REGISTRY, Collector

LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

HTTP_REQUESTS = Counter("nexadesk_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram(
    "nexadesk_http_request_duration_seconds", "HTTP request latency", ["method", "route"], buckets=LATENCY_BUCKETS
)
JOBS = Counter("nexadesk_jobs_total", "Background jobs finished", ["kind", "status"])
JOB_DURATION = Histogram(
    "nexadesk_job_duration_seconds", "Background job run time", ["kind"], buckets=LATENCY_BUCKETS + (30.0, 60.0)
)
AGENT_RUN = Histogram(
    "nexadesk_agent_run_duration_seconds", "Triage agent run time (plan+validate+record)", buckets=LATENCY_BUCKETS
)
AI_STEPS = Counter("nexadesk_ai_steps_total", "Triage agent step outcomes", ["kind", "outcome"])
AI_DECISIONS = Counter("nexadesk_ai_decisions_total", "Human decisions on AI recommendations", ["kind", "decision"])
LLM_CALLS = Counter("nexadesk_llm_calls_total", "Text-generation calls", ["feature", "status"])
LLM_TOKENS = Counter("nexadesk_llm_tokens_total", "Text-generation tokens", ["feature", "direction"])
KB_QUERIES = Counter("nexadesk_kb_queries_total", "Knowledge-base searches/questions", ["mode", "outcome"])


class DatabaseGauges(Collector):
    """Backlog read from PostgreSQL at scrape time."""

    def collect(self):
        from sqlalchemy import func

        from app.db.database import SessionLocal, utcnow
        from app.db.models import AIMonitoringRun, AIPrediction, EmailOutbox, Job, KBDocument

        db = SessionLocal()
        try:
            jobs = GaugeMetricFamily("nexadesk_jobs", "Background jobs by status", labels=["status"])
            for status, n in db.query(Job.status, func.count(Job.id)).group_by(Job.status):
                jobs.add_metric([status], n)
            yield jobs
            oldest = db.query(func.min(Job.run_after)).filter(Job.status.in_(("queued", "failed"))).scalar()
            yield GaugeMetricFamily(
                "nexadesk_jobs_oldest_due_age_seconds",
                "Age of the oldest due job",
                value=max(0.0, (utcnow() - oldest).total_seconds()) if oldest else 0.0,
            )
            yield GaugeMetricFamily(
                "nexadesk_ai_recommendations_awaiting_decision",
                "Proposed AI recommendations",
                value=db.query(func.count(AIPrediction.id)).filter(AIPrediction.status == "proposed").scalar() or 0,
            )
            outbox = GaugeMetricFamily("nexadesk_email_outbox", "Email outbox by status", labels=["status"])
            for status, n in db.query(EmailOutbox.status, func.count(EmailOutbox.id)).group_by(EmailOutbox.status):
                outbox.add_metric([status], n)
            yield outbox
            latest = (
                db.query(AIMonitoringRun.tenant_id, func.max(AIMonitoringRun.id)).group_by(AIMonitoringRun.tenant_id)
            ).subquery()
            drifting = (
                db.query(func.count(AIMonitoringRun.id))
                .join(latest, AIMonitoringRun.id == latest.c[1])
                .filter(AIMonitoringRun.status == "alert")
                .scalar()
            )
            yield GaugeMetricFamily(
                "nexadesk_ai_drift_alerts", "Organizations whose latest AI monitoring run alerted", value=drifting or 0
            )
            yield GaugeMetricFamily(
                "nexadesk_kb_documents_processing",
                "Knowledge-base documents waiting to be indexed",
                value=db.query(func.count(KBDocument.id)).filter(KBDocument.status == "processing").scalar() or 0,
            )
        except Exception:  # a scrape must never take the process down  # noqa: BLE001
            return
        finally:
            db.close()


_db_gauges = DatabaseGauges()


def registry() -> CollectorRegistry:
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        reg = CollectorRegistry()
        multiprocess.MultiProcessCollector(reg)
    else:
        reg = REGISTRY
    return reg


def render(include_db: bool = True) -> tuple[bytes, str]:
    reg = registry()
    if include_db:
        tmp = CollectorRegistry()
        tmp.register(_db_gauges)
        return generate_latest(reg) + generate_latest(tmp), CONTENT_TYPE_LATEST
    return generate_latest(reg), CONTENT_TYPE_LATEST


class timer:
    """Context manager observing elapsed seconds on a histogram (with labels)."""

    def __init__(self, histogram, **labels):
        self.h = histogram.labels(**labels) if labels else histogram

    def __enter__(self):
        self.t = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.h.observe(time.perf_counter() - self.t)
        return False


def serve_worker_metrics(port: int) -> None:
    """Worker scrape endpoint on the internal network, with the same bearer
    token as the API's /metrics when METRICS_TOKEN is set."""
    import hmac
    import threading
    from wsgiref.simple_server import WSGIRequestHandler, make_server

    from prometheus_client import make_wsgi_app

    from app.core.config import settings

    inner = make_wsgi_app(registry())

    def app(environ, start_response):
        if settings.metrics_token:
            supplied = environ.get("HTTP_AUTHORIZATION", "").removeprefix("Bearer ").strip()
            if not hmac.compare_digest(supplied.encode(), settings.metrics_token.encode()):
                start_response("401 Unauthorized", [("Content-Type", "text/plain")])
                return [b"unauthorized"]
        return inner(environ, start_response)

    class _Quiet(WSGIRequestHandler):
        def log_message(self, *args):  # scrapes every 15 s would flood the logs
            pass

    server = make_server("0.0.0.0", port, app, handler_class=_Quiet)  # noqa: S104  # nosec B104 -- container-internal port, token-protected
    threading.Thread(target=server.serve_forever, daemon=True, name="metrics").start()
