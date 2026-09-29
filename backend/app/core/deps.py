from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.rbac import P, has_permission
from app.core.security import decode_access_token
from app.db.database import get_db
from app.db.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def user_from_token(token: str | None, db: Session) -> User | None:
    if not token:
        return None
    payload = decode_access_token(token)
    if payload is None:
        return None
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


def get_current_user(token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    user = user_from_token(token, db)
    if user is None:
        raise _UNAUTHENTICATED
    return user


def get_org_user(user: User = Depends(get_current_user)) -> User:
    """A signed-in user that belongs to an organization. Every org-scoped
    endpoint depends on this, so `user.tenant_id` is always the tenant filter."""
    if user.tenant_id is None:
        raise HTTPException(status_code=403, detail="This action requires organization membership")
    return user


def require_permission(permission: P):
    def dependency(user: User = Depends(get_org_user)) -> User:
        if not has_permission(user.role, permission):
            raise HTTPException(status_code=403, detail="You do not have permission to perform this action")
        return user

    dependency.__name__ = f"require_{permission.value.replace(':', '_')}"
    return dependency


def require_platform_admin(user: User = Depends(get_current_user)) -> User:
    if not has_permission(user.role, P.PLATFORM_ADMIN):
        raise HTTPException(status_code=403, detail="Platform administrator access required")
    return user
