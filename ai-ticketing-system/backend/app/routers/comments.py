from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import TicketComment, Ticket, User
from app.schemas.comments import CommentCreate, CommentOut
from app.core.security import get_current_user

router = APIRouter(
    prefix="/comments",
    tags=["comments"]
)


# ================================
# ADD COMMENT TO A TICKET
# ================================
@router.post("/{ticket_id}", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
def add_comment(
    ticket_id: int,
    comment: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    # tenant security
    if ticket.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    new_comment = TicketComment(
        content=comment.content,
        ticket_id=ticket_id
    )

    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)

    return new_comment


# ================================
# GET ALL COMMENTS OF A TICKET
# ================================
@router.get("/{ticket_id}", response_model=list[CommentOut])
def get_comments(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    return db.query(TicketComment).filter(
        TicketComment.ticket_id == ticket_id
    ).all()
