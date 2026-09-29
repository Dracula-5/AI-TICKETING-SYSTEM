import uuid
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.limiter import limiter
from app.core.rbac import Role, permissions_for
from app.core.request_context import get_request_context
from app.core.security import (
    burn_password_check,
    create_access_token,
    get_password_hash,
    hash_token,
    new_opaque_token,
    verify_password,
)
from app.db.database import get_db, utcnow
from app.db.models import Invitation, RefreshToken, TeamMember, Tenant, User, UserToken
from app.schemas.auth import (
    AcceptInvitationIn,
    EmailIn,
    InvitationPreviewOut,
    RegisterRequest,
    ResetPasswordIn,
    TokenIn,
    TokenOut,
)
from app.schemas.common import MessageOut
from app.schemas.users import MeOut
from app.services import audit
from app.services.email import deliver_pending, password_reset_email, queue_email, verification_email
from app.services.organizations import create_organization, org_setting

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "nexadesk_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _issue_session(db: Session, response: Response, user: User, family_id: str | None = None) -> TokenOut:
    raw = new_opaque_token()
    ctx = get_request_context()
    db.add(
        RefreshToken(
            user_id=user.id,
            family_id=family_id or str(uuid.uuid4()),
            token_hash=hash_token(raw),
            expires_at=utcnow() + timedelta(days=settings.refresh_token_expire_days),
            user_agent=(ctx.user_agent or "")[:255] or None,
            ip=ctx.ip,
        )
    )
    response.set_cookie(
        REFRESH_COOKIE,
        raw,
        max_age=settings.refresh_token_expire_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )
    token, expires_in = create_access_token(user.id, user.tenant_id, user.role)
    return TokenOut(access_token=token, expires_in=expires_in)


def _clear_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


def _send_verification(db: Session, user: User) -> None:
    raw = new_opaque_token()
    db.add(
        UserToken(
            user_id=user.id,
            purpose="email_verification",
            token_hash=hash_token(raw),
            expires_at=utcnow() + timedelta(hours=settings.email_token_expire_hours),
        )
    )
    subject, body = verification_email(user.name, raw)
    queue_email(db, to=user.email, subject=subject, body=body, template="email_verification", tenant_id=user.tenant_id)


def _consume_user_token(db: Session, raw: str, purpose: str) -> UserToken:
    token = db.query(UserToken).filter(UserToken.token_hash == hash_token(raw), UserToken.purpose == purpose).first()
    if token is None or token.used_at is not None or token.expires_at < utcnow():
        raise HTTPException(status_code=400, detail="This link is invalid or has expired")
    token.used_at = utcnow()
    return token


def _load_invitation(db: Session, raw: str) -> Invitation:
    inv = db.query(Invitation).filter(Invitation.token_hash == hash_token(raw)).first()
    if inv is None or inv.accepted_at or inv.revoked_at or inv.expires_at < utcnow():
        raise HTTPException(status_code=400, detail="This invitation is invalid or has expired")
    return inv


def build_me(db: Session, user: User) -> MeOut:
    team_ids = [tid for (tid,) in db.query(TeamMember.team_id).filter(TeamMember.user_id == user.id)]
    org = db.get(Tenant, user.tenant_id) if user.tenant_id else None
    return MeOut.model_validate(
        {
            **{
                c: getattr(user, c)
                for c in (
                    "id",
                    "name",
                    "email",
                    "role",
                    "tenant_id",
                    "is_active",
                    "email_verified_at",
                    "last_login_at",
                    "created_at",
                )
            },
            "organization": org,
            "permissions": sorted(p.value for p in permissions_for(user.role)),
            "team_ids": team_ids,
        }
    )


# ---------------------------------------------------------------------------
# Registration & login
# ---------------------------------------------------------------------------
@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def register(
    request: Request,
    response: Response,
    payload: RegisterRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    email = _normalize_email(payload.email)
    if db.query(User.id).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    if payload.organization_name:
        tenant = create_organization(db, payload.organization_name)
        role = Role.ORG_ADMIN
        audit.record(
            db,
            "org.create",
            tenant_id=tenant.id,
            actor_type="anonymous",
            entity_type="organization",
            entity_id=tenant.id,
            changes={"name": tenant.name},
        )
    else:
        tenant = db.query(Tenant).filter(Tenant.slug == payload.join_slug).first()
        if tenant is None or not org_setting(tenant, "portal_signup_enabled"):
            raise HTTPException(status_code=404, detail="This organization's portal is not open for sign-up")
        allowed = org_setting(tenant, "portal_allowed_domains")
        if allowed and email.rsplit("@", 1)[-1] not in allowed:
            raise HTTPException(status_code=403, detail="Sign-up requires an email address from your organization")
        role = Role.CUSTOMER

    user = User(
        name=payload.name.strip(),
        email=email,
        hashed_password=get_password_hash(payload.password),
        role=role.value,
        tenant_id=tenant.id,
        data_origin=tenant.data_origin,
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        "auth.register",
        tenant_id=tenant.id,
        actor=user,
        entity_type="user",
        entity_id=user.id,
        changes={"role": role.value, "via": "new_org" if payload.organization_name else "portal"},
    )
    _send_verification(db, user)
    user.last_login_at = utcnow()
    tokens = _issue_session(db, response, user)
    db.commit()
    background.add_task(deliver_pending)
    return tokens


@router.post("/login", response_model=TokenOut)
@limiter.limit("20/minute")
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    email = _normalize_email(form_data.username)
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        burn_password_check(form_data.password)
    if user is None or not verify_password(form_data.password, user.hashed_password):
        audit.record(
            db,
            "auth.login_failed",
            tenant_id=user.tenant_id if user else None,
            actor_type="anonymous",
            entity_type="user",
            entity_id=user.id if user else None,
        )
        db.commit()
        raise HTTPException(
            status_code=401, detail="Incorrect email or password", headers={"WWW-Authenticate": "Bearer"}
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account has been deactivated")

    user.last_login_at = utcnow()
    audit.record(db, "auth.login", tenant_id=user.tenant_id, actor=user, entity_type="user", entity_id=user.id)
    tokens = _issue_session(db, response, user)
    db.commit()
    return tokens


@router.post("/refresh", response_model=TokenOut)
@limiter.limit("60/minute")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise HTTPException(status_code=401, detail="No session")
    token = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_token(raw)).first()
    now = utcnow()
    if token is None or token.revoked_at is not None or token.expires_at < now:
        _clear_cookie(response)
        raise HTTPException(status_code=401, detail="Session expired")

    if token.rotated_at is not None:
        # A token that was already exchanged is being replayed: assume theft and
        # end every session in this family.
        db.query(RefreshToken).filter(
            RefreshToken.family_id == token.family_id, RefreshToken.revoked_at.is_(None)
        ).update({RefreshToken.revoked_at: now}, synchronize_session=False)
        user = db.get(User, token.user_id)
        audit.record(
            db,
            "auth.refresh_token_reuse",
            tenant_id=user.tenant_id if user else None,
            actor_type="system",
            entity_type="user",
            entity_id=token.user_id,
        )
        db.commit()
        _clear_cookie(response)
        raise HTTPException(status_code=401, detail="Session expired")

    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        _clear_cookie(response)
        raise HTTPException(status_code=401, detail="Session expired")

    token.rotated_at = now
    tokens = _issue_session(db, response, user, family_id=token.family_id)
    db.commit()
    return tokens


@router.post("/logout", response_model=MessageOut)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        token = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_token(raw)).first()
        if token is not None:
            db.query(RefreshToken).filter(
                RefreshToken.family_id == token.family_id, RefreshToken.revoked_at.is_(None)
            ).update({RefreshToken.revoked_at: utcnow()}, synchronize_session=False)
            user = db.get(User, token.user_id)
            audit.record(
                db,
                "auth.logout",
                tenant_id=user.tenant_id if user else None,
                actor=user,
                entity_type="user",
                entity_id=token.user_id,
            )
            db.commit()
    _clear_cookie(response)
    return {"message": "Signed out"}


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return build_me(db, user)


# ---------------------------------------------------------------------------
# Email verification & password reset
# ---------------------------------------------------------------------------
@router.post("/verify-email", response_model=MessageOut)
@limiter.limit("20/minute")
def verify_email(request: Request, payload: TokenIn, db: Session = Depends(get_db)):
    token = _consume_user_token(db, payload.token, "email_verification")
    user = db.get(User, token.user_id)
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
        audit.record(
            db, "auth.email_verified", tenant_id=user.tenant_id, actor=user, entity_type="user", entity_id=user.id
        )
    db.commit()
    return {"message": "Email verified"}


@router.post("/resend-verification", response_model=MessageOut)
@limiter.limit("3/minute")
def resend_verification(
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.email_verified_at is not None:
        return {"message": "Email already verified"}
    _send_verification(db, user)
    db.commit()
    background.add_task(deliver_pending)
    return {"message": "Verification email sent"}


@router.post("/forgot-password", response_model=MessageOut, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/minute")
def forgot_password(request: Request, payload: EmailIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    # Same response whether or not the account exists (no account enumeration).
    user = db.query(User).filter(User.email == _normalize_email(payload.email)).first()
    if user is not None and user.is_active:
        tenant = db.get(Tenant, user.tenant_id) if user.tenant_id else None
        if not (tenant and tenant.is_demo):
            raw = new_opaque_token()
            db.add(
                UserToken(
                    user_id=user.id,
                    purpose="password_reset",
                    token_hash=hash_token(raw),
                    expires_at=utcnow() + timedelta(minutes=settings.password_reset_expire_minutes),
                )
            )
            subject, body = password_reset_email(user.name, raw)
            queue_email(
                db, to=user.email, subject=subject, body=body, template="password_reset", tenant_id=user.tenant_id
            )
            audit.record(
                db,
                "auth.password_reset_requested",
                tenant_id=user.tenant_id,
                actor_type="anonymous",
                entity_type="user",
                entity_id=user.id,
            )
            db.commit()
            background.add_task(deliver_pending)
    return {"message": "If an account exists for that email, a reset link is on its way"}


@router.post("/reset-password", response_model=MessageOut)
@limiter.limit("10/minute")
def reset_password(request: Request, payload: ResetPasswordIn, db: Session = Depends(get_db)):
    token = _consume_user_token(db, payload.token, "password_reset")
    user = db.get(User, token.user_id)
    user.hashed_password = get_password_hash(payload.new_password)
    # Sign out every existing session.
    db.query(RefreshToken).filter(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).update(
        {RefreshToken.revoked_at: utcnow()}, synchronize_session=False
    )
    audit.record(db, "auth.password_reset", tenant_id=user.tenant_id, actor=user, entity_type="user", entity_id=user.id)
    db.commit()
    return {"message": "Password updated. Sign in with your new password."}


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------
@router.get("/invitations/{token}", response_model=InvitationPreviewOut)
@limiter.limit("30/minute")
def preview_invitation(request: Request, token: str, db: Session = Depends(get_db)):
    inv = _load_invitation(db, token)
    return InvitationPreviewOut(
        organization_name=inv.tenant.name,
        email=inv.email,
        role=inv.role,
        invited_by=inv.invited_by.name,
    )


@router.post("/accept-invitation", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def accept_invitation(request: Request, response: Response, payload: AcceptInvitationIn, db: Session = Depends(get_db)):
    inv = _load_invitation(db, payload.token)
    if db.query(User.id).filter(User.email == inv.email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    tenant = db.get(Tenant, inv.tenant_id)
    user = User(
        name=payload.name.strip(),
        email=inv.email,
        hashed_password=get_password_hash(payload.password),
        role=inv.role,
        tenant_id=inv.tenant_id,
        data_origin=tenant.data_origin,
        # The invitation link was delivered to this address, which proves ownership.
        email_verified_at=utcnow(),
    )
    db.add(user)
    db.flush()
    if inv.team_id:
        db.add(TeamMember(team_id=inv.team_id, user_id=user.id))
    inv.accepted_at = utcnow()
    audit.record(
        db,
        "user.invitation_accepted",
        tenant_id=inv.tenant_id,
        actor=user,
        entity_type="invitation",
        entity_id=inv.id,
        changes={"role": inv.role},
    )
    user.last_login_at = utcnow()
    tokens = _issue_session(db, response, user)
    db.commit()
    return tokens
