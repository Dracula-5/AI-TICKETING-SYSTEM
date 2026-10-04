"""Platform-operator console. Counts, activity and system health across
organizations — platform admins do not get read access to organizations'
tickets, comments or articles through these routes.

GET    /platform/overview                 totals split by data origin, AI and background-system state
GET    /platform/organizations            one row of aggregates per organization
GET    /platform/users                    most recent sign-ups (account, role, organization)
DELETE /platform/organizations/{id}       delete an organization with all its data (audited)
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai import llm
from app.core.config import settings
from app.core.deps import require_platform_admin
from app.db.database import get_db, utcnow
from app.db.models import AIPrediction, EmailOutbox, Feedback, Job, KBDocument, Tenant, Ticket, User
from app.schemas.analytics import PlatformOverviewOut
from app.services import audit
from app.services.organizations import delete_organization
from app.services.tickets import OPEN_STATUSES

router = APIRouter(prefix="/platform", tags=["platform"])

_OPEN = [s.value for s in OPEN_STATUSES]


class OrganizationRow(BaseModel):
    id: int
    name: str
    slug: str
    is_demo: bool
    data_origin: str
    created_at: datetime
    users: int
    active_users_7d: int
    tickets: int
    open_tickets: int
    tickets_7d: int
    sla_breached_open: int
    last_ticket_at: datetime | None
    kb_documents: int
    ai_pending: int
    csat_average: float | None
    csat_responses: int


class PlatformUserRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: str
    is_active: bool
    organization: str | None
    data_origin: str
    created_at: datetime
    last_login_at: datetime | None


def _counts(db: Session, column, *criteria) -> dict[int, int]:
    """{tenant_id: count} for one grouped query."""
    return dict(db.query(column, func.count()).filter(*criteria).group_by(column).all())


@router.get("/overview", response_model=PlatformOverviewOut)
def platform_overview(_: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    week_ago = utcnow() - timedelta(days=7)
    provider = llm.get_llm()
    return PlatformOverviewOut(
        organizations=db.query(func.count(Tenant.id)).scalar(),
        demo_organizations=db.query(func.count(Tenant.id)).filter(Tenant.is_demo.is_(True)).scalar(),
        users_by_origin=dict(db.query(User.data_origin, func.count(User.id)).group_by(User.data_origin).all()),
        tickets_by_origin=dict(db.query(Ticket.data_origin, func.count(Ticket.id)).group_by(Ticket.data_origin).all()),
        active_users_7d_real=db.query(func.count(User.id))
        .filter(User.data_origin == "real", User.last_login_at >= week_ago, User.tenant_id.isnot(None))
        .scalar(),
        open_tickets=db.query(func.count(Ticket.id)).filter(Ticket.status.in_(_OPEN)).scalar(),
        tickets_7d=db.query(func.count(Ticket.id)).filter(Ticket.created_at >= week_ago).scalar(),
        sla_breached_open=db.query(func.count(Ticket.id))
        .filter(Ticket.status.in_(_OPEN), Ticket.resolution_breached_at.isnot(None))
        .scalar(),
        jobs_by_status=dict(db.query(Job.status, func.count(Job.id)).group_by(Job.status).all()),
        emails_by_status=dict(
            db.query(EmailOutbox.status, func.count(EmailOutbox.id)).group_by(EmailOutbox.status).all()
        ),
        ai_enabled=settings.ai_enabled,
        embedding_model=settings.embedding_model if settings.ai_enabled else None,
        text_generation=provider is not None,
        environment=settings.environment,
        release=settings.release,
        background_mode=settings.background_mode,
        email_backend=settings.email_backend,
    )


@router.get("/organizations", response_model=list[OrganizationRow])
def platform_organizations(_: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    week_ago = utcnow() - timedelta(days=7)
    users = _counts(db, User.tenant_id, User.tenant_id.isnot(None))
    active = _counts(db, User.tenant_id, User.tenant_id.isnot(None), User.last_login_at >= week_ago)
    tickets = _counts(db, Ticket.tenant_id)
    open_tickets = _counts(db, Ticket.tenant_id, Ticket.status.in_(_OPEN))
    recent = _counts(db, Ticket.tenant_id, Ticket.created_at >= week_ago)
    breached = _counts(db, Ticket.tenant_id, Ticket.status.in_(_OPEN), Ticket.resolution_breached_at.isnot(None))
    documents = _counts(db, KBDocument.tenant_id)
    pending = _counts(db, AIPrediction.tenant_id, AIPrediction.status == "proposed")
    last_ticket = dict(db.query(Ticket.tenant_id, func.max(Ticket.created_at)).group_by(Ticket.tenant_id).all())
    csat = {
        tid: (float(avg), n)
        for tid, avg, n in db.query(Feedback.tenant_id, func.avg(Feedback.rating), func.count(Feedback.id))
        .filter(Feedback.kind == "csat", Feedback.rating.isnot(None))
        .group_by(Feedback.tenant_id)
    }
    return [
        OrganizationRow(
            id=t.id,
            name=t.name,
            slug=t.slug,
            is_demo=t.is_demo,
            data_origin=t.data_origin,
            created_at=t.created_at,
            users=users.get(t.id, 0),
            active_users_7d=active.get(t.id, 0),
            tickets=tickets.get(t.id, 0),
            open_tickets=open_tickets.get(t.id, 0),
            tickets_7d=recent.get(t.id, 0),
            sla_breached_open=breached.get(t.id, 0),
            last_ticket_at=last_ticket.get(t.id),
            kb_documents=documents.get(t.id, 0),
            ai_pending=pending.get(t.id, 0),
            csat_average=round(csat[t.id][0], 2) if t.id in csat else None,
            csat_responses=csat[t.id][1] if t.id in csat else 0,
        )
        for t in db.query(Tenant).order_by(Tenant.created_at.desc(), Tenant.id.desc())
    ]


@router.get("/users", response_model=list[PlatformUserRow])
def platform_users(
    limit: int = Query(default=50, ge=1, le=200),
    _: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(User, Tenant.name)
        .outerjoin(Tenant, Tenant.id == User.tenant_id)
        .order_by(User.created_at.desc(), User.id.desc())
        .limit(limit)
        .all()
    )
    return [
        PlatformUserRow(
            id=u.id,
            name=u.name,
            email=u.email,
            role=u.role,
            is_active=u.is_active,
            organization=org,
            data_origin=u.data_origin,
            created_at=u.created_at,
            last_login_at=u.last_login_at,
        )
        for u, org in rows
    ]


@router.delete("/organizations/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
def platform_delete_organization(
    tenant_id: int,
    confirm: str = Query(description="The organization's slug, to guard against deleting the wrong one"),
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if confirm != tenant.slug:
        raise HTTPException(status_code=400, detail="Confirmation does not match the organization's slug")
    summary = {
        "name": tenant.name,
        "slug": tenant.slug,
        "is_demo": tenant.is_demo,
        "users": db.query(func.count(User.id)).filter(User.tenant_id == tenant.id).scalar(),
        "tickets": db.query(func.count(Ticket.id)).filter(Ticket.tenant_id == tenant.id).scalar(),
    }
    delete_organization(db, tenant)
    # tenant_id=None: the organization's own audit rows are gone with it; this one stays.
    audit.record(
        db,
        "platform.org.delete",
        tenant_id=None,
        actor=admin,
        entity_type="organization",
        entity_id=tenant_id,
        changes=summary,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
