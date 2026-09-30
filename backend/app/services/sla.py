"""
SLA sweep: records first-response and resolution breaches, escalates tickets
whose resolution SLA is breached, and auto-closes resolved tickets the
requester never confirmed.

Safe to run concurrently from several processes: candidate rows are selected
with FOR UPDATE SKIP LOCKED on PostgreSQL (two sweepers never process the same
ticket), and every update is guarded by the "not yet recorded" condition, so a
re-run is a no-op. SQLite ignores the row lock, which is acceptable for its
single-process dev/test use.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, false, or_
from sqlalchemy.orm import Session

from app.db.database import utcnow
from app.db.models import SlaPolicy, Tenant, Ticket
from app.services import audit
from app.services.notification_service import notify_many
from app.services.organizations import org_setting
from app.services.tickets import TERMINAL_STATUSES, TicketStatus, staff_lead_ids, transition

logger = logging.getLogger(__name__)

_OPEN = [s.value for s in TicketStatus if s not in TERMINAL_STATUSES]
BATCH = 200
# Fraction of the SLA window left at which an open ticket counts as "at risk".
AT_RISK_FRACTION = 0.25


def _locked(query):
    return query.with_for_update(skip_locked=True).limit(BATCH)


def run_sla_sweep(db: Session, now=None) -> dict:
    now = now or utcnow()
    result = {"first_response_breaches": 0, "resolution_breaches": 0, "escalated": 0, "auto_closed": 0}

    first_response = _locked(
        db.query(Ticket).filter(
            Ticket.status.in_(_OPEN),
            Ticket.first_responded_at.is_(None),
            Ticket.first_response_breached_at.is_(None),
            Ticket.first_response_due.isnot(None),
            Ticket.first_response_due < now,
        )
    ).all()
    for t in first_response:
        t.first_response_breached_at = now
        audit.record(
            db,
            "sla.first_response_breached",
            tenant_id=t.tenant_id,
            actor_type="system",
            entity_type="ticket",
            entity_id=t.id,
            changes={"due": t.first_response_due.isoformat()},
        )
        notify_many(
            db,
            t.tenant_id,
            {t.assigned_to_user_id, *staff_lead_ids(db, t.tenant_id)},
            type_="sla_breach",
            title=f"First-response SLA breached: #{t.number} {t.title}",
            message=f"Priority {t.priority}",
            link=f"/tickets/{t.id}",
        )
        result["first_response_breaches"] += 1
    db.commit()

    resolution = _locked(
        db.query(Ticket).filter(
            Ticket.status.in_(_OPEN),
            Ticket.sla_paused_at.is_(None),
            Ticket.resolution_breached_at.is_(None),
            Ticket.resolution_due.isnot(None),
            Ticket.resolution_due < now,
        )
    ).all()
    for t in resolution:
        t.resolution_breached_at = now
        audit.record(
            db,
            "sla.resolution_breached",
            tenant_id=t.tenant_id,
            actor_type="system",
            entity_type="ticket",
            entity_id=t.id,
            changes={"due": t.resolution_due.isoformat()},
        )
        result["resolution_breaches"] += 1
        if t.status != TicketStatus.ESCALATED.value:
            # transition() notifies the assignee and the org's managers.
            transition(
                db,
                t,
                TicketStatus.ESCALATED,
                actor=None,
                actor_type="system",
                reason="Resolution SLA breached",
                enforce=False,
            )
            result["escalated"] += 1
    db.commit()

    resolved = _locked(
        db.query(Ticket)
        .filter(
            Ticket.status == TicketStatus.RESOLVED.value,
            Ticket.resolved_at.isnot(None),
        )
        .order_by(Ticket.resolved_at)
    ).all()
    tenants: dict[int, Tenant] = {}
    for t in resolved:
        tenant = tenants.get(t.tenant_id) or db.get(Tenant, t.tenant_id)
        if tenant is None or t.resolved_at is None:
            continue
        tenants[t.tenant_id] = tenant
        days = int(org_setting(tenant, "auto_close_days"))
        if now - t.resolved_at >= timedelta(days=days):
            transition(
                db,
                t,
                TicketStatus.CLOSED,
                actor=None,
                actor_type="system",
                reason=f"Auto-closed {days} days after resolution without a reply",
                enforce=False,
            )
            result["auto_closed"] += 1
    db.commit()

    if any(result.values()):
        logger.info("sla_sweep", extra=result)
    return result


def at_risk_clause(db: Session, tenant_id: int, now: datetime):
    """Open, not breached, not paused, and inside the last 25% of the
    resolution window for its priority (per this org's policies)."""
    policies = db.query(SlaPolicy).filter(SlaPolicy.tenant_id == tenant_id).all()
    per_priority = [
        and_(
            Ticket.priority == p.priority,
            Ticket.resolution_due <= now + timedelta(minutes=p.resolution_minutes * AT_RISK_FRACTION),
        )
        for p in policies
    ]
    return and_(
        Ticket.resolution_breached_at.is_(None),
        Ticket.first_response_breached_at.is_(None),
        Ticket.sla_paused_at.is_(None),
        Ticket.resolution_due > now,
        or_(*per_priority) if per_priority else false(),
    )
