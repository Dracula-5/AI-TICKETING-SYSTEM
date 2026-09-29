from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from app.core.deps import require_permission
from app.core.rbac import P
from app.db.database import get_db
from app.db.models import AuditLog, User
from app.schemas.analytics import AuditLogOut
from app.schemas.common import Page

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=Page[AuditLogOut])
def list_audit_logs(
    action: str | None = Query(
        default=None, max_length=64, description="Exact action or prefix ending in '.', e.g. 'ticket.'"
    ),
    entity_type: str | None = None,
    entity_id: str | None = None,
    actor_user_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user: User = Depends(require_permission(P.AUDIT_READ)),
    db: Session = Depends(get_db),
):
    q = db.query(AuditLog).filter(AuditLog.tenant_id == user.tenant_id)
    if action:
        q = q.filter(AuditLog.action.like(f"{action}%") if action.endswith(".") else AuditLog.action == action)
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.filter(AuditLog.entity_id == entity_id)
    if actor_user_id is not None:
        q = q.filter(AuditLog.actor_user_id == actor_user_id)
    if since:
        q = q.filter(AuditLog.created_at >= since)
    if until:
        q = q.filter(AuditLog.created_at < until)
    total = q.count()
    rows = (
        q.options(joinedload(AuditLog.actor))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        AuditLogOut(
            id=r.id,
            actor_type=r.actor_type,
            actor_name=r.actor.name if r.actor else None,
            actor_email=r.actor.email if r.actor else None,
            action=r.action,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            changes=r.changes,
            ip=r.ip,
            request_id=r.request_id,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)
