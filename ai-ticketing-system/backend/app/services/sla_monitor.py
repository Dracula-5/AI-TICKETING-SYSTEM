from datetime import datetime
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.db.models import Ticket

def check_sla():
    db: Session = SessionLocal()

    tickets = db.query(Ticket).filter(
        Ticket.sla_due < datetime.utcnow(),
        Ticket.is_escalated == False,
        Ticket.status != "resolved",
        Ticket.status != "closed"
    ).all()

    for t in tickets:
        t.is_escalated = True
        t.status = "escalated"
        print(f"🚨 Ticket {t.id} escalated!")

    db.commit()
    db.close()
if __name__ == "__main__":
    check_sla() 

    