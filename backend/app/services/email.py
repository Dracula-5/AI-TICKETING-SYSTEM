"""
Outgoing email via a transactional outbox.

`queue_email()` inserts an EmailOutbox row in the caller's transaction.
`deliver_pending()` sends queued rows with the configured backend and records
the outcome; it runs after the request (FastAPI BackgroundTasks) and will move
to the background worker in P2. Delivery failures never fail the request that
queued the email — the row stays `failed` with its error for retry/inspection.
"""

import logging
import smtplib
from email.message import EmailMessage

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


def deliver_pending(session_factory=SessionLocal, limit: int = 50) -> int:
    db = session_factory()
    sent = 0
    try:
        rows = (
            db.query(EmailOutbox)
            .filter(EmailOutbox.status.in_(["queued", "failed"]), EmailOutbox.attempts < MAX_ATTEMPTS)
            .order_by(EmailOutbox.id)
            .limit(limit)
            .all()
        )
        for row in rows:
            row.attempts += 1
            try:
                _send(row)
                row.status, row.sent_at, row.last_error = "sent", utcnow(), None
                sent += 1
            except Exception as exc:  # delivery errors are recorded, not raised
                row.status, row.last_error = "failed", str(exc)[:1000]
                logger.warning("email_delivery_failed", extra={"email_id": row.id})
            db.commit()
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
