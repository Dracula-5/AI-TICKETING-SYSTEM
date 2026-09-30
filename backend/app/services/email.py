"""
Outgoing email via a transactional outbox.

Producer → queue → worker → result → retry → dead letter:

* `queue_email()` inserts an EmailOutbox row in the caller's transaction, so an
  email exists if and only if the change that caused it committed.
* `deliver_pending()` is the consumer: the worker process runs it every few
  seconds (BACKGROUND_MODE=worker); in single-process development the API
  runs it after the response instead (BACKGROUND_MODE=inline).
* Failures are retried with exponential backoff and parked as `dead` after
  MAX_ATTEMPTS. Delivery never fails the request that queued the email.
"""

import logging
import smtplib
from datetime import timedelta
from email.message import EmailMessage

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import SessionLocal, utcnow
from app.db.models import EmailOutbox

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5


def queue_email(
    db: Session, *, to: str, subject: str, body: str, template: str, tenant_id: int | None = None
) -> EmailOutbox:
    row = EmailOutbox(tenant_id=tenant_id, to_email=to, subject=subject, body_text=body, template=template)
    db.add(row)
    return row


def _send_smtp(row: EmailOutbox) -> None:
    msg = EmailMessage()
    msg["From"] = settings.email_from
    msg["To"] = row.to_email
    msg["Subject"] = row.subject
    msg.set_content(row.body_text)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(msg)


def _send(row: EmailOutbox) -> None:
    if settings.email_backend == "smtp":
        _send_smtp(row)
    else:
        # Console backend: the email is fully readable in the outbox table
        # (and via /api/v1/dev/outbox in development); log only metadata so
        # tokens embedded in links never reach log aggregation.
        logger.info("email_console_delivery", extra={"email_id": row.id, "template": row.template})


def schedule_delivery(background) -> None:
    """Deliver right after the response in single-process mode; with a worker,
    the worker's poll picks the message up within EMAIL_POLL_INTERVAL_SECONDS."""
    if settings.background_mode == "inline":
        background.add_task(deliver_pending)


def _backoff(attempts: int) -> timedelta:
    # 1, 2, 4, 8 … minutes, capped at an hour.
    return timedelta(minutes=min(2 ** max(attempts - 1, 0), 60))


def deliver_pending(session_factory=SessionLocal, limit: int = 50) -> int:
    """Drain the outbox. Each message is claimed in its own transaction with
    FOR UPDATE SKIP LOCKED, so any number of workers can run this concurrently
    without sending a message twice. Failures are retried with exponential
    backoff; after MAX_ATTEMPTS the message is parked as `dead` (dead letter)."""
    sent = 0
    for _ in range(limit):
        db = session_factory()
        try:
            now = utcnow()
            row = (
                db.query(EmailOutbox)
                .filter(
                    EmailOutbox.status.in_(["queued", "failed"]),
                    or_(EmailOutbox.next_attempt_at.is_(None), EmailOutbox.next_attempt_at <= now),
                )
                .order_by(EmailOutbox.id)
                .with_for_update(skip_locked=True)
                .first()
            )
            if row is None:
                break
            row.attempts += 1
            try:
                _send(row)
                row.status, row.sent_at, row.last_error, row.next_attempt_at = "sent", utcnow(), None, None
                sent += 1
            except Exception as exc:  # delivery errors are recorded, not raised
                row.last_error = str(exc)[:1000]
                if row.attempts >= MAX_ATTEMPTS:
                    row.status, row.next_attempt_at = "dead", None
                    logger.error("email_dead_lettered", extra={"email_id": row.id, "attempts": row.attempts})
                else:
                    row.status, row.next_attempt_at = "failed", now + _backoff(row.attempts)
                    logger.warning("email_delivery_failed", extra={"email_id": row.id, "attempts": row.attempts})
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("email_delivery_loop_failed")
            break
        finally:
            db.close()
    return sent


# ---------------------------------------------------------------------------
# Templates (plain text; HTML templates can come with a real provider in P2)
# ---------------------------------------------------------------------------
def _link(path: str) -> str:
    return f"{settings.frontend_base_url.rstrip('/')}{path}"


def verification_email(name: str, token: str) -> tuple[str, str]:
    return (
        f"Verify your {settings.app_name} email address",
        f"Hi {name},\n\nConfirm your email address by opening this link:\n{_link('/verify-email?token=' + token)}\n\n"
        f"The link expires in {settings.email_token_expire_hours} hours.",
    )


def password_reset_email(name: str, token: str) -> tuple[str, str]:
    return (
        f"Reset your {settings.app_name} password",
        f"Hi {name},\n\nSomeone asked to reset your password. If it was you, open:\n"
        f"{_link('/reset-password?token=' + token)}\n\n"
        f"The link expires in {settings.password_reset_expire_minutes} minutes. "
        "If you did not ask for this, ignore this email.",
    )


def invitation_email(org_name: str, inviter: str, role: str, invite_url: str) -> tuple[str, str]:
    return (
        f"{inviter} invited you to {org_name} on {settings.app_name}",
        f"{inviter} invited you to join {org_name} as {role.replace('_', ' ')}.\n\n"
        f"Accept the invitation:\n{invite_url}\n\n"
        f"The invitation expires in {settings.invitation_expire_days} days.",
    )


def invite_url(token: str) -> str:
    return _link("/accept-invite?token=" + token)
