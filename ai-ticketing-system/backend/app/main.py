import logging
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import func, text

from app.core.cache import cache_get, cache_set
from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import setup_logging
from app.db.database import SessionLocal
from app.db.init_db import init_db
from app.db.models import NegotiationSession, Order, Product, Ticket, User, Vendor
from app.routers import analytics, auth, comments, negotiations, notifications, orders, products, providers, sla, tenant, ticket, users, vendors
from app.services.sla_monitor import check_sla

setup_logging()
logger = logging.getLogger(__name__)

METRICS_CACHE_KEY = "metrics:global"
METRICS_CACHE_TTL = 10

# The committed fallback in app/core/config.py — if this is still the active
# secret_key at startup, JWTs are forgeable by anyone who reads the public repo.
_DEFAULT_SECRET_KEY = "TDwXmO7vcIeybQPYU8UNXYLtIGdqeP-yxcQKRTreR4WIzfIqwFW2z_WOkjSfUQP2"


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
def _parse_cors_origins(value: str) -> list[str]:
    raw = [part.strip() for part in value.replace(";", ",").split(",")]
    return [o.rstrip("/") for o in raw if o] or []


def _sla_background_job():
    while True:
        try:
            check_sla()
        except Exception:
            logger.exception("sla_background_job_iteration_failed")
        time.sleep(30)


# ---------------------------------------------------------------------------
# Lifespan (replaces deprecated on_event)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.secret_key == _DEFAULT_SECRET_KEY:
        logger.warning(
            "SECRET_KEY is still the committed default — JWTs are forgeable by anyone "
            "who reads this public repo. Set a real SECRET_KEY before deploying."
        )

    init_db()
    if settings.seed_marketplace_demo_data:
        from app.scripts.seed_marketplace import seed_marketplace
        try:
            seed_marketplace()
        except Exception:
            logger.exception("Error seeding marketplace demo data")
    threading.Thread(target=_sla_background_job, daemon=True).start()
    yield


app = FastAPI(
    title="AI Ticketing System",
    description=(
        "Production-grade multi-tenant support ticketing platform with "
        "AI-powered routing, SLA monitoring, and price negotiation."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

origins = _parse_cors_origins(settings.cors_origins) or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=(origins != ["*"]),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request logging + security headers
# ---------------------------------------------------------------------------
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(tenant.router)
app.include_router(ticket.router)
app.include_router(comments.router)
app.include_router(users.router)
app.include_router(providers.router)
app.include_router(sla.router)
app.include_router(vendors.router)
app.include_router(products.router)
app.include_router(negotiations.router)
app.include_router(orders.router)
app.include_router(analytics.router)
app.include_router(notifications.router)


# ---------------------------------------------------------------------------
# Catch-all exception handler -- an uncaught error anywhere below should
# still log full request context and return a generic JSON body instead of
# leaking a stack trace or an unstructured framework error page.
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "unhandled_exception",
        extra={"method": request.method, "path": request.url.path},
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ---------------------------------------------------------------------------
# Health / readiness
# ---------------------------------------------------------------------------
@app.get("/", tags=["meta"])
def home():
    return {"message": "AI Ticketing System backend running"}


@app.get("/health", tags=["meta"])
def health(response: Response):
    db_status = "ok"
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except Exception:
        logger.exception("health_check_db_unreachable")
        db_status = "unreachable"

    if db_status != "ok":
        response.status_code = 503
    return {"status": "ok" if db_status == "ok" else "degraded", "database": db_status}


@app.get("/ready", tags=["meta"])
def ready():
    return {"status": "ready"}


@app.get("/ping", tags=["meta"])
def ping():
    return {"message": "pong"}


# ---------------------------------------------------------------------------
# Live metrics endpoint
# ---------------------------------------------------------------------------
@app.get("/metrics", tags=["meta"])
@limiter.limit("60/minute")
def metrics(request: Request):
    """
    Live operational metrics aggregated from the database.
    Intended for the admin dashboard and portfolio demo.
    All numbers reflect real database state—no hardcoded values.
    """
    cached = cache_get(METRICS_CACHE_KEY)
    if cached is not None:
        return cached

    db = SessionLocal()
    try:
        total_tickets = db.query(func.count(Ticket.id)).scalar() or 0
        open_tickets = db.query(func.count(Ticket.id)).filter(Ticket.status == "open").scalar() or 0
        resolved_tickets = db.query(func.count(Ticket.id)).filter(Ticket.status == "resolved").scalar() or 0
        escalated_tickets = db.query(func.count(Ticket.id)).filter(Ticket.is_escalated == True).scalar() or 0  # noqa: E712
        total_users = db.query(func.count(User.id)).scalar() or 0

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        non_escalated = db.query(func.count(Ticket.id)).filter(
            Ticket.is_escalated == False,  # noqa: E712
            Ticket.status != "open",
        ).scalar() or 0
        closed_or_resolved = db.query(func.count(Ticket.id)).filter(
            Ticket.status.in_(["resolved", "closed"])
        ).scalar() or 0

        sla_compliance_pct = (
            round((closed_or_resolved - escalated_tickets) / closed_or_resolved * 100, 1)
            if closed_or_resolved > 0
            else 100.0
        )

        by_priority = {
            row[0]: row[1]
            for row in db.query(Ticket.priority, func.count(Ticket.id))
            .group_by(Ticket.priority)
            .all()
        }
        by_category = {
            row[0]: row[1]
            for row in db.query(Ticket.category, func.count(Ticket.id))
            .group_by(Ticket.category)
            .all()
        }
        by_status = {
            row[0]: row[1]
            for row in db.query(Ticket.status, func.count(Ticket.id))
            .group_by(Ticket.status)
            .all()
        }

        total_vendors = db.query(func.count(Vendor.id)).scalar() or 0
        total_products = db.query(func.count(Product.id)).scalar() or 0
        total_orders = db.query(func.count(Order.id)).scalar() or 0
        total_negotiations = db.query(func.count(NegotiationSession.id)).scalar() or 0

        result = {
            "generated_at": now.isoformat() + "Z",
            "tickets": {
                "total": total_tickets,
                "open": open_tickets,
                "resolved": resolved_tickets,
                "escalated": escalated_tickets,
                "by_priority": by_priority,
                "by_category": by_category,
                "by_status": by_status,
            },
            "sla_compliance_pct": sla_compliance_pct,
            "total_users": total_users,
            "marketplace": {
                "total_vendors": total_vendors,
                "total_products": total_products,
                "total_orders": total_orders,
                "total_negotiations": total_negotiations,
            },
        }
        cache_set(METRICS_CACHE_KEY, result, METRICS_CACHE_TTL)
        return result
    finally:
        db.close()
