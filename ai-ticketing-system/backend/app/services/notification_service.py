"""
Creates and broadcasts Notification rows. Every business operation that
triggers a notification (ticket created, offer made, order placed, ...)
must succeed regardless of whether the alert can be delivered -- callers
are expected to wrap notify()/create_notification() in a try/except so a
notification hiccup never breaks the underlying operation.
"""
import logging

from sqlalchemy.orm import Session

from app.db.models import Notification
from app.schemas.notifications import NotificationOut
from app.services.notification_ws import manager

logger = logging.getLogger(__name__)


def create_notification(
    db: Session,
    tenant_id: int,
    user_id: int,
    type_: str,
    title: str,
    message: str | None = None,
    link: str | None = None,
) -> Notification:
    entry = Notification(
        tenant_id=tenant_id,
        user_id=user_id,
        type=type_,
        title=title,
        message=message,
        link=link,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


async def notify(
    db: Session,
    tenant_id: int,
    user_id: int,
    type_: str,
    title: str,
    message: str | None = None,
    link: str | None = None,
) -> Notification | None:
    try:
        entry = create_notification(db, tenant_id, user_id, type_, title, message, link)
    except Exception:
        logger.exception("Failed to persist notification for user %s", user_id)
        return None

    try:
        payload = NotificationOut.model_validate(entry).model_dump(mode="json")
        await manager.send_to_user(user_id, payload)
    except Exception:
        logger.exception("Failed to broadcast notification %s to user %s", entry.id, user_id)

    return entry
