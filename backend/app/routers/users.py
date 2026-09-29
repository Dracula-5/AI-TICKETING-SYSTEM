from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.limiter import limiter
from app.core.security import get_password_hash, verify_password
from app.db.database import get_db, utcnow
from app.db.models import RefreshToken, User
from app.routers.auth import build_me
from app.schemas.auth import PasswordChangeIn
from app.schemas.common import MessageOut
from app.schemas.users import MeOut, ProfileUpdate
from app.services import audit
from app.services.guards import ensure_not_demo

router = APIRouter(prefix="/users", tags=["users"])


@router.patch("/me", response_model=MeOut)
def update_profile(payload: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.name.strip() != user.name:
        audit.record(
            db,
            "user.profile_update",
            tenant_id=user.tenant_id,
            actor=user,
            entity_type="user",
            entity_id=user.id,
            changes={"name": [user.name, payload.name.strip()]},
        )
        user.name = payload.name.strip()
        db.commit()
    return build_me(db, user)


@router.put("/me/password", response_model=MessageOut)
@limiter.limit("5/minute")
def change_password(
    request: Request, payload: PasswordChangeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    ensure_not_demo(db, user, "Changing the password of a shared demo account")
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.hashed_password = get_password_hash(payload.new_password)
    # Other sessions are signed out; the current access token stays valid until it expires.
    db.query(RefreshToken).filter(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).update(
        {RefreshToken.revoked_at: utcnow()}, synchronize_session=False
    )
    audit.record(
        db, "auth.password_change", tenant_id=user.tenant_id, actor=user, entity_type="user", entity_id=user.id
    )
    db.commit()
    return {"message": "Password updated"}
