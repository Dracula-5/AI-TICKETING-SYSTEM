"""
Notifications are written in the caller's transaction and pushed over the
WebSocket only after that transaction commits, so users are never told about
a change that was rolled back.

With Redis available the push is published to every API process
(services/realtime.py), so it also works from the background worker. Without
Redis, endpoints (plain `def` handlers in Starlette's thread pool) hand the
push to the local event loop with `anyio.from_thread.run`; outside a request
there is no loop to hand to, but the row is stored and the user sees it on
their next fetch.
"""

import logging

import anyio
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db.models import Notification
from app.schemas.notifications import NotificationOut
from app.services.notification_ws import manager
from app.services.realtime import publish

logger = logging.getLogger(__name__)

_PENDING_KEY = "pending_realtime_push"


def notify(
    db: Session,
    tenant_id: int,
    user_id: int,
    type_: str,
    title: str,
    message: str | None = None,
    link: str | None = None,
) -> Notification:
    entry = Notification(tenant_id=tenant_id, user_id=user_id, type=type_, title=title, message=message, link=link)
    db.add(entry)
    db.flush()
    payload = NotificationOut.model_validate(entry).model_dump(mode="json")
    db.info.setdefault(_PENDING_KEY, []).append((user_id, {"type": "notification", "data": payload}))
    return entry


def notify_many(db: Session, tenant_id: int, user_ids, **kwargs) -> None:
    for uid in sorted(set(u for u in user_ids if u)):
        notify(db, tenant_id, uid, **kwargs)


@event.listens_for(Session, "after_commit")
def _push_after_commit(session: Session) -> None:
    pending = session.info.pop(_PENDING_KEY, None)
    if not pending:
        return
    for user_id, payload in pending:
        # Preferred path: Redis pub/sub reaches every API process (and works
        # from the background worker). Fallback: this process's own sockets.
        if publish(user_id, payload):
            continue
        try:
            anyio.from_thread.run(manager.send_to_user, user_id, payload)
        except RuntimeError:
            # Not running inside an AnyIO worker thread (e.g. a script).
            return
        except Exception:
            logger.exception("notification_push_failed", extra={"user_id": user_id})


@event.listens_for(Session, "after_rollback")
def _discard_after_rollback(session: Session) -> None:
    session.info.pop(_PENDING_KEY, None)
