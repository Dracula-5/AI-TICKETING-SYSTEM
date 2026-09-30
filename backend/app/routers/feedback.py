"""
Feedback from people using NexaDesk (P9).

POST /tickets/{id}/csat        requester rates a resolved ticket (1–5, once; may update)
POST /feedback                 anyone signed in: product feedback
GET  /feedback                 managers/admins: the organization's feedback
GET  /analytics/pilot          pilot metrics (computed; see app/services/pilot.py)
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.deps import current_org, get_org_user, org_id, require_permission
from app.core.rbac import P
from app.db.database import get_db
from app.db.models import Feedback, Ticket, User
from app.services import pilot

router = APIRouter(tags=["feedback"])


class CsatIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class ProductFeedbackIn(BaseModel):
    comment: str = Field(min_length=3, max_length=4000)
    page: str | None = Field(default=None, max_length=200)
    rating: int | None = Field(default=None, ge=1, le=5)


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    ticket_id: int | None
    rating: int | None
    comment: str | None
    page: str | None
    data_origin: str
    created_at: datetime


@router.post("/tickets/{ticket_id}/csat", response_model=FeedbackOut)
def rate_ticket(ticket_id: int, payload: CsatIn, user: User = Depends(get_org_user), db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id, Ticket.tenant_id == org_id(user)).first()
    if ticket is None or ticket.created_by_user_id != user.id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.status not in ("resolved", "closed"):
        raise HTTPException(status_code=409, detail="Rate a ticket once it has been resolved")
    row = db.query(Feedback).filter(Feedback.ticket_id == ticket.id, Feedback.kind == "csat").first()
    if row is None:
        row = Feedback(
            tenant_id=ticket.tenant_id,
            user_id=user.id,
            kind="csat",
            ticket_id=ticket.id,
            data_origin=ticket.data_origin,
        )
        db.add(row)
    row.rating, row.comment = payload.rating, (payload.comment or "").strip() or None
    db.commit()
    db.refresh(row)
    return row


@router.post("/feedback", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
def product_feedback(payload: ProductFeedbackIn, user: User = Depends(get_org_user), db: Session = Depends(get_db)):
    org = current_org(db, user)
    row = Feedback(
        tenant_id=org.id,
        user_id=user.id,
        kind="product",
        rating=payload.rating,
        comment=payload.comment.strip(),
        page=payload.page,
        data_origin=org.data_origin,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/feedback", response_model=list[FeedbackOut])
def list_feedback(
    kind: str | None = None, user: User = Depends(require_permission(P.ANALYTICS_READ)), db: Session = Depends(get_db)
):
    q = db.query(Feedback).filter(Feedback.tenant_id == org_id(user))
    if kind:
        q = q.filter(Feedback.kind == kind)
    return q.order_by(Feedback.created_at.desc()).limit(500).all()


@router.get("/analytics/pilot")
def pilot_metrics(
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(require_permission(P.ANALYTICS_READ)),
    db: Session = Depends(get_db),
) -> dict:
    return pilot.compute(db, current_org(db, user), days)
