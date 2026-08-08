import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import Ticket

logger = logging.getLogger(__name__)


def check_sla():
    db: Session = SessionLocal()
    try:
        tickets = db.query(Ticket).filter(
            Ticket.sla_due < datetime.now(timezone.utc).replace(tzinfo=None),
            Ticket.is_escalated == False,
            Ticket.status != "resolved",
            Ticket.status != "closed"
        ).all()

        for t in tickets:
            t.is_escalated = True
            t.status = "escalated"
            logger.warning("ticket_sla_escalated", extra={"ticket_id": t.id})

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    check_sla()
