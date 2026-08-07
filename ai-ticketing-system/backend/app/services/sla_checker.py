
from datetime import datetime, timezone
from app.db.models import Ticket

def check_and_escalate_sla(db):
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    breached = db.query(Ticket).filter(
        Ticket.sla_due < now,
        Ticket.status != "closed",
        Ticket.is_escalated == False
    ).all()

    for ticket in breached:
        ticket.is_escalated = True

    db.commit()
    return len(breached)




