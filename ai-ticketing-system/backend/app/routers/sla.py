from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from app.db.database import get_db
from app.db.models import Ticket

router = APIRouter(prefix="/sla", tags=["sla"])

@router.put("/check")
def check_sla(db: Session = Depends(get_db)):
    now = datetime.utcnow()

    tickets = db.query(Ticket).filter(
        Ticket.status != "closed",
        Ticket.sla_due < now,
        Ticket.is_escalated == False
    ).all()

    for t in tickets:
        t.is_escalated = True

    db.commit()

    return {"escalated": len(tickets)}
