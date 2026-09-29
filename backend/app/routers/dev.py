"""Development-only helpers. main.py mounts this router only when
ENVIRONMENT is development or test — never in staging/production."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import EmailOutbox

router = APIRouter(prefix="/dev", tags=["development"])


class OutboxItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    to_email: str
    subject: str
    body_text: str
    template: str
    status: str


@router.get("/outbox", response_model=list[OutboxItem])
def outbox(to: str | None = None, limit: int = Query(default=20, le=100), db: Session = Depends(get_db)):
    """Emails the console backend 'sent' — lets you click verification,
    reset and invitation links locally without an SMTP server."""
    q = db.query(EmailOutbox)
    if to:
        q = q.filter(EmailOutbox.to_email == to.lower())
    return q.order_by(EmailOutbox.id.desc()).limit(limit).all()
