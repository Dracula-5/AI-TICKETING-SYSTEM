import asyncio
import hmac
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager

import anyio
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.core import metrics
from app.core.cache import get_redis
from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import setup_logging
from app.core.monitoring import init_error_monitoring
from app.core.request_context import RequestContext, reset_request_context, set_request_context
from app.db.database import SessionLocal
from app.routers import (
    ai,
    analytics,
    audit_logs,
    auth,
    dev,
    feedback,
    kb,
    notifications,
    org_config,
    organizations,
    platform,
    tickets,
    users,
)
from app.services.notification_ws import manager as ws_manager
from app.services.realtime import run_subscriber

setup_logging()
logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def _sla_sweep_once() -> None:
    from app.services.sla import run_sla_sweep

    db = SessionLocal()
    try:
        run_sla_sweep(db)
    except Exception:
        db.rollback()
        logger.exception("sla_sweep_failed")
    finally:
        db.close()


async def _sla_loop() -> None:
    # BACKGROUND_MODE=inline only (single-process development). In deployed
    # environments the worker process owns this; either way run_sla_sweep is
    # idempotent and uses SKIP LOCKED, so an overlap is harmless.
    while True:
        await anyio.to_thread.run_sync(_sla_sweep_once)
        await asyncio.sleep(settings.sla_sweep_interval_seconds)


async def _jobs_loop() -> None:
    # BACKGROUND_MODE=inline only: run queued jobs (AI triage, knowledge-base
    # indexing) in-process. Independent of the SLA sweep setting.
    from app.services.jobs import run_due_jobs

    while True:
        await anyio.to_thread.run_sync(run_due_jobs)
        await asyncio.sleep(settings.job_poll_interval_seconds)


def _seed_demo() -> None:
    # Runs in a worker thread after start-up, not before it: on a small host the
    # seed takes minutes, and a deploy must not wait for demo content.
    import os

    if not os.environ.get("DEMO_PASSWORD"):
        logger.warning("demo_seed_skipped", extra={"reason": "DEMO_PASSWORD is not set"})
        return
    from app.scripts import seed_demo

    started = time.perf_counter()
    try:
        result = seed_demo.seed()
    except Exception:
        logger.exception("demo_seed_failed")
        return
    logger.info(
        "demo_seed",
        extra={
            "created": [o["org"] for o in result["created"]],
            "seconds": round(time.perf_counter() - started, 1),
        },
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_for_environment()
    init_error_monitoring("api")
    tasks: list[asyncio.Task] = []
    if settings.background_mode == "inline" and settings.sla_sweep_enabled:
        tasks.append(asyncio.create_task(_sla_loop()))
    if settings.background_mode == "inline" and settings.job_runner_enabled:
        tasks.append(asyncio.create_task(_jobs_loop()))
    if settings.ai_enabled and settings.environment != "test":
        # Load the embedding model in the background at start-up; lazily, the first
        # KB search or analysis in each process paid ~3 s (P10 load test).
        from app.ai.embedder import get_embedder

        tasks.append(asyncio.create_task(anyio.to_thread.run_sync(get_embedder)))
    if settings.seed_demo_on_start and settings.environment != "test":
        tasks.append(asyncio.create_task(anyio.to_thread.run_sync(_seed_demo)))
    if get_redis() is not None:
        # Cross-process WebSocket fan-out (services/realtime.py).
        tasks.append(asyncio.create_task(run_subscriber(ws_manager)))
    logger.info(
        "startup",
        extra={
            "environment": settings.environment,
            "background_mode": settings.background_mode,
            "realtime": "redis" if get_redis() is not None else "in-process",
        },
    )
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(
    title=f"{settings.app_name} API",
    description=(
        "Multi-tenant service-management API: organizations, RBAC, ticket lifecycle with SLA clocks, "
        "comments and attachments, audit trail, and operational analytics."
    ),
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    incoming = request.headers.get("x-request-id", "")
    request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
    token = set_request_context(
        RequestContext(
            request_id=request_id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        # Unhandled errors become a 500 in the outer error middleware; count them here,
        # or the 5xx metrics and alert never see them (found in the P10 load test).
        route = getattr(request.scope.get("route"), "path", "unmatched")
        if request.url.path.startswith(API_PREFIX) and not route.startswith(API_PREFIX) and route != "unmatched":
            route = API_PREFIX + route
        metrics.HTTP_REQUESTS.labels(request.method, route, "500").inc()
        metrics.HTTP_LATENCY.labels(request.method, route).observe(time.perf_counter() - start)
        raise
    finally:
        reset_request_context(token)
    elapsed = time.perf_counter() - start
    duration_ms = round(elapsed * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    # Route template, not the raw path, so ids do not explode label cardinality.
    route = getattr(request.scope.get("route"), "path", "unmatched")
    if request.url.path.startswith(API_PREFIX) and not route.startswith(API_PREFIX) and route != "unmatched":
        route = API_PREFIX + route  # included routers report their path without the mount prefix
    metrics.HTTP_REQUESTS.labels(request.method, route, str(response.status_code)).inc()
    metrics.HTTP_LATENCY.labels(request.method, route).observe(elapsed)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if not request.url.path.startswith(("/api/docs", "/api/redoc")):
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    logger.info(
        "request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled_exception", extra={"method": request.method, "path": request.url.path})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


for module in (
    auth,
    users,
    organizations,
    org_config,
    tickets,
    notifications,
    analytics,
    audit_logs,
    platform,
    ai,
    kb,
    feedback,
):
    app.include_router(module.router, prefix=API_PREFIX)
app.include_router(tickets.attachments_router, prefix=API_PREFIX)
if settings.environment in ("development", "test"):
    app.include_router(dev.router, prefix=API_PREFIX)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health", tags=["meta"])
def health():
    """Liveness: the process is up and serving requests."""
    return {"status": "ok"}


@app.get("/ready", tags=["meta"])
def ready(response: Response):
    """Readiness: the database answers and its schema is at the migration head."""
    checks = {"database": "ok", "migrations": "unknown"}
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        try:
            current = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
            checks["migrations"] = "ok" if current == _alembic_head() else f"behind ({current})"
        except Exception:
            db.rollback()
            checks["migrations"] = "not managed by alembic"
    except Exception:
        logger.exception("readiness_db_unreachable")
        checks["database"] = "unreachable"
    finally:
        db.close()
    healthy = checks["database"] == "ok" and checks["migrations"] in ("ok", "not managed by alembic")
    if not healthy:
        response.status_code = 503
    return {"status": "ready" if healthy else "not_ready", **checks}


_HEAD: str | None = None


def _alembic_head() -> str | None:
    global _HEAD
    if _HEAD is None:
        from pathlib import Path

        from alembic.config import Config
        from alembic.script import ScriptDirectory

        backend_dir = Path(__file__).resolve().parents[1]
        cfg = Config(str(backend_dir / "alembic.ini"))
        cfg.set_main_option("script_location", str(backend_dir / "alembic"))
        _HEAD = ScriptDirectory.from_config(cfg).get_current_head()
    return _HEAD


@app.get("/metrics", include_in_schema=False)
def prometheus_metrics(request: Request) -> Response:
    """Prometheus scrape endpoint. Internal network only (Caddy routes nothing
    here) and, when METRICS_TOKEN is set (required when deployed), bearer-protected."""
    if settings.metrics_token:
        supplied = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(supplied.encode(), settings.metrics_token.encode()):
            return Response(status_code=401)
    body, content_type = metrics.render()
    return Response(content=body, media_type=content_type)
