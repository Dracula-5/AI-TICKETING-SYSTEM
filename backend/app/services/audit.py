"""
Audit trail. `record()` adds the entry to the caller's session without
committing, so the audit row and the change it describes commit (or roll
back) together — there is never a change without its audit entry.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.core.request_context import get_request_context
from app.db.models import AuditLog, User


def record(
    db: Session,
    action: str,
    *,
    tenant_id: int | None,
    actor: User | None = None,
    actor_type: str | None = None,
    entity_type: str | None = None,
    entity_id: Any = None,
    changes: dict | None = None,
) -> AuditLog:
    ctx = get_request_context()
    entry = AuditLog(
        tenant_id=tenant_id,
        actor_user_id=actor.id if actor else None,
        actor_type=actor_type or ("user" if actor else "system"),
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        changes=changes,
        ip=ctx.ip,
        user_agent=(ctx.user_agent or "")[:255] or None,
        request_id=ctx.request_id,
    )
    db.add(entry)
    return entry


def diff(before: dict, after: dict) -> dict:
    """{field: [old, new]} for fields whose value changed."""
    return {k: [before.get(k), v] for k, v in after.items() if before.get(k) != v}
