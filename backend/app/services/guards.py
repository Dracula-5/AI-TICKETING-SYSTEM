from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import Tenant, User


def ensure_not_demo(db: Session, user: User, what: str = "This action") -> None:
    """Shared demo organizations use published credentials, so actions that
    could lock other visitors out or send email to arbitrary addresses are
    disabled there. Everything else (tickets, comments, workflow) works."""
    tenant = db.get(Tenant, user.tenant_id) if user.tenant_id else None
    if tenant is not None and tenant.is_demo:
        raise HTTPException(
            status_code=403,
            detail=f"{what} is disabled in the shared demo organization. Create your own organization to try it.",
        )
