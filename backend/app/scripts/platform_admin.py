"""
Create (or re-key) the platform administrator from the environment.

    PLATFORM_ADMIN_EMAIL=ops@example.org PLATFORM_ADMIN_PASSWORD=... python -m app.scripts.platform_admin

The platform administrator belongs to no organization and signs in to the
platform console (/platform): totals, per-organization activity, sign-ups and
background-system health — aggregates only, never ticket content. The role
cannot be granted in the app, so this is the only way to create one; on hosts
without a shell the container entrypoint runs it at start-up when both
variables are set (app/scripts/prestart.py).

Idempotent: an existing platform administrator with that email gets the
password from the environment (so rotating the variable rotates the password);
an email that belongs to an organization member is refused.
"""

import os
import sys

from app.core.rbac import Role
from app.core.security import get_password_hash, verify_password
from app.db.database import SessionLocal, utcnow
from app.db.models import User
from app.schemas.auth import _check_password
from app.services import audit


def ensure(email: str, password: str) -> str:
    """Returns "created", "password updated" or "unchanged"; raises ValueError on bad input."""
    email = email.strip().lower()
    if "@" not in email:
        raise ValueError("PLATFORM_ADMIN_EMAIL is not an email address")
    _check_password(password)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(
                name="Platform administrator",
                email=email,
                hashed_password=get_password_hash(password),
                role=Role.PLATFORM_ADMIN.value,
                tenant_id=None,
                email_verified_at=utcnow(),
            )
            db.add(user)
            db.flush()
            outcome = "created"
        elif user.role != Role.PLATFORM_ADMIN.value or user.tenant_id is not None:
            raise ValueError(f"{email} already belongs to an organization member; choose another address")
        elif verify_password(password, user.hashed_password):
            return "unchanged"
        else:
            user.hashed_password = get_password_hash(password)
            outcome = "password updated"
        audit.record(db, f"platform.admin.{outcome.split()[0]}", tenant_id=None, entity_type="user", entity_id=user.id)
        db.commit()
        return outcome
    finally:
        db.close()


def run() -> None:
    email, password = os.environ.get("PLATFORM_ADMIN_EMAIL", ""), os.environ.get("PLATFORM_ADMIN_PASSWORD", "")
    if not email or not password:
        print("PLATFORM_ADMIN_EMAIL and PLATFORM_ADMIN_PASSWORD must both be set.", file=sys.stderr)
        return
    try:
        print(f"Platform administrator {email.strip().lower()}: {ensure(email, password)}.", flush=True)
    except ValueError as e:
        # A bad value must not keep the whole API from starting.
        print(f"Platform administrator not configured: {e}", file=sys.stderr)


if __name__ == "__main__":
    run()
