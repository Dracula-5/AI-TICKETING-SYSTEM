"""Platform-operator endpoints. Aggregates only — platform admins do not get
read access to organizations' tickets through these routes."""

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import require_platform_admin
from app.db.database import get_db, utcnow
from app.db.models import Tenant, Ticket, User
from app.schemas.analytics import PlatformOverviewOut

router = APIRouter(prefix="/platform", tags=["platform"])


@router.get("/overview", response_model=PlatformOverviewOut)
def platform_overview(_: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    week_ago = utcnow() - timedelta(days=7)
    return PlatformOverviewOut(
        organizations=db.query(func.count(Tenant.id)).scalar(),
        demo_organizations=db.query(func.count(Tenant.id)).filter(Tenant.is_demo.is_(True)).scalar(),
        users_by_origin=dict(db.query(User.data_origin, func.count(User.id)).group_by(User.data_origin).all()),
        tickets_by_origin=dict(db.query(Ticket.data_origin, func.count(Ticket.id)).group_by(Ticket.data_origin).all()),
        active_users_7d_real=db.query(func.count(User.id))
        .filter(User.data_origin == "real", User.last_login_at >= week_ago, User.tenant_id.isnot(None))
        .scalar(),
    )
