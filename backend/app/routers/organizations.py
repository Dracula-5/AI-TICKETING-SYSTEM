from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import current_org, org_id, require_permission
from app.core.limiter import limiter
from app.core.rbac import GRANTABLE_ROLES, P, Role
from app.core.security import hash_token, new_opaque_token
from app.db.database import get_db, utcnow
from app.db.models import Invitation, RefreshToken, Team, Tenant, User
from app.schemas.common import MessageOut, Page
from app.schemas.organizations import (
    InvitationCreate,
    InvitationCreatedOut,
    InvitationOut,
    OrganizationOut,
    OrganizationUpdate,
    PortalInfoOut,
)
from app.schemas.users import MemberUpdate, UserOut
from app.services import audit
from app.services.email import invitation_email, invite_url, queue_email, schedule_delivery
from app.services.guards import ensure_not_demo
from app.services.organizations import DEFAULT_ORG_SETTINGS, org_setting

router = APIRouter(prefix="/organizations", tags=["organizations"])

# Managers may bring in staff and requesters but not grant admin rights.
_MANAGER_INVITABLE = frozenset({Role.AGENT, Role.CUSTOMER, Role.ANALYST})


def _org_out(tenant: Tenant) -> OrganizationOut:
    return OrganizationOut.model_validate(
        {
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "is_demo": tenant.is_demo,
            "settings": {**DEFAULT_ORG_SETTINGS, **(tenant.settings or {})},
            "created_at": tenant.created_at,
        }
    )


@router.get("/me", response_model=OrganizationOut)
def get_my_org(user: User = Depends(require_permission(P.ORG_READ)), db: Session = Depends(get_db)):
    return _org_out(current_org(db, user))


@router.patch("/me", response_model=OrganizationOut)
def update_my_org(
    payload: OrganizationUpdate,
    user: User = Depends(require_permission(P.ORG_UPDATE)),
    db: Session = Depends(get_db),
):
    ensure_not_demo(db, user, "Changing organization settings")
    tenant = current_org(db, user)
    before = {"name": tenant.name, "settings": {**DEFAULT_ORG_SETTINGS, **(tenant.settings or {})}}
    if payload.name is not None:
        tenant.name = payload.name.strip()
    if payload.settings is not None:
        tenant.settings = payload.settings.model_dump()
    after = {"name": tenant.name, "settings": {**DEFAULT_ORG_SETTINGS, **(tenant.settings or {})}}
    changes = audit.diff(before, after)
    if changes:
        audit.record(
            db,
            "org.update",
            tenant_id=tenant.id,
            actor=user,
            entity_type="organization",
            entity_id=tenant.id,
            changes=changes,
        )
    db.commit()
    return _org_out(tenant)


@router.get("/portal/{slug}", response_model=PortalInfoOut)
@limiter.limit("30/minute")
def portal_info(request: Request, slug: str, db: Session = Depends(get_db)):
    """Public: what the /join/<slug> page needs. 404 unless the org opted in,
    so the endpoint cannot be used to enumerate organizations."""
    tenant = db.query(Tenant).filter(Tenant.slug == slug).first()
    if tenant is None or not org_setting(tenant, "portal_signup_enabled"):
        raise HTTPException(status_code=404, detail="Portal not found")
    return PortalInfoOut(
        name=tenant.name,
        slug=tenant.slug,
        signup_enabled=True,
        allowed_domains=org_setting(tenant, "portal_allowed_domains"),
    )


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------
@router.get("/me/members", response_model=Page[UserOut])
def list_members(
    role: str | None = None,
    q: str | None = Query(default=None, max_length=100),
    include_inactive: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user: User = Depends(require_permission(P.USERS_READ)),
    db: Session = Depends(get_db),
):
    query = db.query(User).filter(User.tenant_id == user.tenant_id)
    if role:
        query = query.filter(User.role.in_(role.split(",")))
    if not include_inactive:
        query = query.filter(User.is_active.is_(True))
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(or_(func.lower(User.name).like(like), func.lower(User.email).like(like)))
    total = query.count()
    items = query.order_by(User.name, User.id).offset((page - 1) * page_size).limit(page_size).all()
    return Page(items=items, total=total, page=page, page_size=page_size)


def _active_admin_count(db: Session, tenant_id: int) -> int:
    return (
        db.query(User.id)
        .filter(User.tenant_id == tenant_id, User.role == Role.ORG_ADMIN.value, User.is_active.is_(True))
        .count()
    )


@router.patch("/me/members/{user_id}", response_model=UserOut)
def update_member(
    user_id: int,
    payload: MemberUpdate,
    user: User = Depends(require_permission(P.USERS_MANAGE)),
    db: Session = Depends(get_db),
):
    ensure_not_demo(db, user, "Changing member roles")
    member = db.query(User).filter(User.id == user_id, User.tenant_id == user.tenant_id).first()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if member.id == user.id:
        raise HTTPException(status_code=409, detail="You cannot change your own role or deactivate yourself")
    if payload.role is not None and payload.role not in GRANTABLE_ROLES:
        raise HTTPException(status_code=422, detail="Unknown role")

    before = {"role": member.role, "is_active": member.is_active}
    removing_admin = member.role == Role.ORG_ADMIN.value and (
        (payload.role is not None and payload.role != Role.ORG_ADMIN.value) or payload.is_active is False
    )
    # Defense in depth: unreachable today (the acting admin is itself an active
    # admin and cannot modify itself), but keeps the invariant if USERS_MANAGE
    # is ever granted to a non-admin role.
    if removing_admin and _active_admin_count(db, org_id(user)) <= 1:
        raise HTTPException(status_code=409, detail="An organization must keep at least one active admin")

    if payload.role is not None:
        member.role = payload.role
    if payload.is_active is not None:
        member.is_active = payload.is_active
        if not payload.is_active:
            db.query(RefreshToken).filter(RefreshToken.user_id == member.id, RefreshToken.revoked_at.is_(None)).update(
                {RefreshToken.revoked_at: utcnow()}, synchronize_session=False
            )
    changes = audit.diff(before, {"role": member.role, "is_active": member.is_active})
    if changes:
        audit.record(
            db,
            "user.update",
            tenant_id=user.tenant_id,
            actor=user,
            entity_type="user",
            entity_id=member.id,
            changes=changes,
        )
    db.commit()
    db.refresh(member)
    return member


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------
@router.get("/me/invitations", response_model=list[InvitationOut])
def list_invitations(user: User = Depends(require_permission(P.USERS_INVITE)), db: Session = Depends(get_db)):
    return (
        db.query(Invitation)
        .filter(
            Invitation.tenant_id == user.tenant_id, Invitation.accepted_at.is_(None), Invitation.revoked_at.is_(None)
        )
        .order_by(Invitation.created_at.desc())
        .limit(200)
        .all()
    )


@router.post("/me/invitations", response_model=InvitationCreatedOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_invitation(
    request: Request,
    payload: InvitationCreate,
    background: BackgroundTasks,
    user: User = Depends(require_permission(P.USERS_INVITE)),
    db: Session = Depends(get_db),
):
    ensure_not_demo(db, user, "Sending invitations")
    if payload.role not in GRANTABLE_ROLES:
        raise HTTPException(status_code=422, detail="Unknown role")
    if user.role == Role.MANAGER.value and payload.role not in _MANAGER_INVITABLE:
        raise HTTPException(status_code=403, detail="Managers can invite agents, requesters and analysts only")
    email = payload.email.strip().lower()
    if db.query(User.id).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    if (
        payload.team_id is not None
        and not db.query(Team.id).filter(Team.id == payload.team_id, Team.tenant_id == user.tenant_id).first()
    ):
        raise HTTPException(status_code=404, detail="Team not found")

    now = utcnow()
    # Re-inviting replaces any outstanding invitation for the same address.
    db.query(Invitation).filter(
        Invitation.tenant_id == user.tenant_id,
        Invitation.email == email,
        Invitation.accepted_at.is_(None),
        Invitation.revoked_at.is_(None),
    ).update({Invitation.revoked_at: now}, synchronize_session=False)

    raw = new_opaque_token()
    inv = Invitation(
        tenant_id=user.tenant_id,
        email=email,
        role=payload.role,
        team_id=payload.team_id,
        token_hash=hash_token(raw),
        invited_by_user_id=user.id,
        expires_at=now + timedelta(days=settings.invitation_expire_days),
    )
    db.add(inv)
    db.flush()
    tenant = current_org(db, user)
    url = invite_url(raw)
    subject, body = invitation_email(tenant.name, user.name, payload.role, url)
    queue_email(db, to=email, subject=subject, body=body, template="invitation", tenant_id=user.tenant_id)
    audit.record(
        db,
        "user.invite",
        tenant_id=user.tenant_id,
        actor=user,
        entity_type="invitation",
        entity_id=inv.id,
        changes={"email": email, "role": payload.role},
    )
    db.commit()
    schedule_delivery(background)
    return InvitationCreatedOut.model_validate({**InvitationOut.model_validate(inv).model_dump(), "invite_url": url})


@router.delete("/me/invitations/{invitation_id}", response_model=MessageOut)
def revoke_invitation(
    invitation_id: int,
    user: User = Depends(require_permission(P.USERS_INVITE)),
    db: Session = Depends(get_db),
):
    inv = db.query(Invitation).filter(Invitation.id == invitation_id, Invitation.tenant_id == user.tenant_id).first()
    if inv is None or inv.accepted_at or inv.revoked_at:
        raise HTTPException(status_code=404, detail="Invitation not found")
    inv.revoked_at = utcnow()
    audit.record(
        db, "user.invitation_revoked", tenant_id=user.tenant_id, actor=user, entity_type="invitation", entity_id=inv.id
    )
    db.commit()
    return {"message": "Invitation revoked"}
