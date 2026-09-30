"""
Operational analytics computed live from the database — no stored or
hard-coded figures. `data_origin` tells the UI whether the numbers describe a
demo organization, so demo metrics are never presented as production usage.
"""

from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.cache import cache_get, cache_set
from app.core.config import settings
from app.core.deps import current_org, org_id, require_permission
from app.core.rbac import P
from app.db.database import get_db, utcnow
from app.db.models import Team, Ticket, User
from app.schemas.analytics import CountItem, OverviewOut, TrendPoint, WorkloadItem
from app.services.sla import at_risk_clause
from app.services.tickets import OPEN_STATUSES

router = APIRouter(prefix="/analytics", tags=["analytics"])

_OPEN = [s.value for s in OPEN_STATUSES]


def seconds_between(db: Session, later, earlier):
    if db.get_bind().dialect.name == "sqlite":
        return (func.julianday(later) - func.julianday(earlier)) * 86400.0
    return func.extract("epoch", later - earlier)


def _counts(rows) -> list[CountItem]:
    return [CountItem(key=k, count=c) for k, c in sorted(rows, key=lambda r: -r[1])]


@router.get("/overview", response_model=OverviewOut)
def overview(user: User = Depends(require_permission(P.ANALYTICS_READ)), db: Session = Depends(get_db)):
    """Dashboard figures, cached per organization for ANALYTICS_CACHE_SECONDS.

    P10 load test: this was the slowest endpoint (p50 530 ms at 250 users on
    100k tickets) and held database connections long enough to exhaust the pool
    at 500 users. The dashboard already refreshes every 30 s, so a 30 s cache
    changes nothing a person can see; `generated_at` still states when the
    figures were computed. Redis down → computed on every request (fail open)."""
    tid = org_id(user)
    key = f"analytics:overview:v1:{tid}"
    if settings.analytics_cache_seconds:
        cached = cache_get(key)
        if cached is not None:
            return OverviewOut.model_validate(cached)
    result = _compute_overview(db, user)
    if settings.analytics_cache_seconds:
        cache_set(key, result.model_dump(mode="json"), settings.analytics_cache_seconds)
    return result


def _compute_overview(db: Session, user: User) -> OverviewOut:
    """Counts and averages for the caller's organization.

    `by_status` covers every ticket; `by_priority`, `by_category`, `by_team`
    and `by_agent` cover open tickets only. 30-day figures use tickets resolved
    (or created, for first response) in the last 30 days. Resolution time is
    wall-clock time from creation to resolution, including time spent waiting
    on the customer."""
    tid = org_id(user)
    now = utcnow()
    day_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    since_30 = now - timedelta(days=30)
    tickets = db.query(Ticket).filter(Ticket.tenant_id == tid)
    open_q = tickets.filter(Ticket.status.in_(_OPEN))

    resolved_30 = tickets.filter(Ticket.resolved_at.isnot(None), Ticket.resolved_at >= since_30)
    avg_res = resolved_30.with_entities(func.avg(seconds_between(db, Ticket.resolved_at, Ticket.created_at))).scalar()
    avg_fr = (
        tickets.filter(Ticket.created_at >= since_30, Ticket.first_responded_at.isnot(None))
        .with_entities(func.avg(seconds_between(db, Ticket.first_responded_at, Ticket.created_at)))
        .scalar()
    )
    resolved_count = resolved_30.count()
    with_sla = resolved_30.filter(Ticket.resolution_due.isnot(None))
    with_sla_count = with_sla.count()
    met = with_sla.filter(Ticket.resolution_breached_at.is_(None), Ticket.first_response_breached_at.is_(None)).count()

    ever_resolved = tickets.filter(
        Ticket.created_at >= since_30, or_(Ticket.resolved_at.isnot(None), Ticket.reopened_count > 0)
    )
    ever_resolved_count = ever_resolved.count()
    reopened = ever_resolved.filter(Ticket.reopened_count > 0).count()

    team_rows = (
        open_q.outerjoin(Team, Team.id == Ticket.team_id)
        .with_entities(Team.id, Team.name, func.count(Ticket.id))
        .group_by(Team.id, Team.name)
        .all()
    )
    agent_rows = (
        open_q.outerjoin(User, User.id == Ticket.assigned_to_user_id)
        .with_entities(User.id, User.name, func.count(Ticket.id))
        .group_by(User.id, User.name)
        .order_by(func.count(Ticket.id).desc())
        .limit(20)
        .all()
    )

    since_14 = datetime.combine((now - timedelta(days=13)).date(), time.min, tzinfo=timezone.utc)
    created_by_day = dict(
        tickets.filter(Ticket.created_at >= since_14)
        .with_entities(func.date(Ticket.created_at), func.count(Ticket.id))
        .group_by(func.date(Ticket.created_at))
        .all()
    )
    resolved_by_day = dict(
        tickets.filter(Ticket.resolved_at.isnot(None), Ticket.resolved_at >= since_14)
        .with_entities(func.date(Ticket.resolved_at), func.count(Ticket.id))
        .group_by(func.date(Ticket.resolved_at))
        .all()
    )
    trend = []
    for i in range(14):
        d = (since_14 + timedelta(days=i)).date()
        key_candidates = (d, d.isoformat())
        trend.append(
            TrendPoint(
                day=d,
                created=next((created_by_day[k] for k in key_candidates if k in created_by_day), 0),
                resolved=next((resolved_by_day[k] for k in key_candidates if k in resolved_by_day), 0),
            )
        )

    tenant = current_org(db, user)
    return OverviewOut(
        generated_at=now,
        data_origin=tenant.data_origin,
        open_tickets=open_q.count(),
        created_today=tickets.filter(Ticket.created_at >= day_start).count(),
        unassigned_open=open_q.filter(Ticket.assigned_to_user_id.is_(None)).count(),
        sla_breached_open=open_q.filter(
            or_(Ticket.first_response_breached_at.isnot(None), Ticket.resolution_breached_at.isnot(None))
        ).count(),
        sla_at_risk_open=open_q.filter(at_risk_clause(db, tid, now)).count(),
        resolved_last_30d=resolved_count,
        avg_first_response_minutes_30d=round(avg_fr / 60, 1) if avg_fr is not None else None,
        avg_resolution_hours_30d=round(avg_res / 3600, 2) if avg_res is not None else None,
        sla_compliance_pct_30d=round(met / with_sla_count * 100, 1) if with_sla_count else None,
        reopen_rate_pct_30d=round(reopened / ever_resolved_count * 100, 1) if ever_resolved_count else None,
        by_status=_counts(tickets.with_entities(Ticket.status, func.count(Ticket.id)).group_by(Ticket.status).all()),
        by_priority=_counts(
            open_q.with_entities(Ticket.priority, func.count(Ticket.id)).group_by(Ticket.priority).all()
        ),
        by_category=_counts(
            open_q.with_entities(Ticket.category, func.count(Ticket.id)).group_by(Ticket.category).all()
        ),
        by_team=[
            WorkloadItem(id=i, name=n or "Unrouted", open=c) for i, n, c in sorted(team_rows, key=lambda r: -r[2])
        ],
        by_agent=[WorkloadItem(id=i, name=n or "Unassigned", open=c) for i, n, c in agent_rows],
        trend_14d=trend,
    )
