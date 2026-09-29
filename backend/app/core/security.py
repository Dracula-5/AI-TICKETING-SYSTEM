import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# bcrypt only reads the first 72 bytes; passwords are length-validated at the
# schema layer so nothing is silently truncated.
BCRYPT_MAX_BYTES = 72


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:BCRYPT_MAX_BYTES], bcrypt.gensalt(rounds=settings.bcrypt_rounds)).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode()[:BCRYPT_MAX_BYTES], hashed_password.encode())
    except ValueError:
        return False


# A real hash of a random string, compared against when the email is unknown,
# so login takes the same time whether or not the account exists.
_DUMMY_HASH = get_password_hash(secrets.token_urlsafe(16))


def burn_password_check(plain_password: str) -> None:
    verify_password(plain_password, _DUMMY_HASH)


def create_access_token(user_id: int, tenant_id: int | None, role: str) -> tuple[str, int]:
    """Short-lived bearer token. Claims are hints for clients; the server
    re-loads the user on every request, so role changes and deactivation take
    effect immediately rather than when the token expires."""
    now = datetime.now(timezone.utc)
    expires_in = settings.access_token_expire_minutes * 60
    payload = {
        "sub": str(user_id),
        "tid": tenant_id,
        "role": role,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm), expires_in


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None
    if payload.get("type") != "access" or not payload.get("sub"):
        return None
    return payload


def new_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
