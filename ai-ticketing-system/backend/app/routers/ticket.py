from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.db.database import get_db
from app.db.models import Ticket, User
from app.schemas.tickets import TicketCreate, TicketOut
from app.core.security import get_current_user

from app.services.auto_router import predict_category
from app.ai.priority import predict_priority
from app.services.sla_checker import check_and_escalate_sla
from fastapi import Body


router = APIRouter(
    prefix="/tickets",
    tags=["tickets"]
)


# ========================
# Create Ticket
# ========================
@router.post("/", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
def create_ticket(
    ticket: TicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    if ticket.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    # AI Auto Category
    category = predict_category(ticket.title, ticket.description)

    # AI Priority
    auto_priority = predict_priority(ticket.description)
    priority = ticket.priority if ticket.priority else auto_priority

    # SLA Times
    if priority == "high":
        sla_hours = 6
    elif priority == "medium":
        sla_hours = 12
    else:
        sla_hours = 24

    sla_due_time = datetime.utcnow() + timedelta(hours=sla_hours)

    new_ticket = Ticket(
        title=ticket.title,
        description=ticket.description,
        priority=priority,
        category=category,
        tenant_id=ticket.tenant_id,
        created_by_user_id=current_user.id,
        sla_due=sla_due_time
    )

    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)

    return new_ticket


# ========================
# Get Ticket by ID
# ========================
@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    return ticket


# ========================
# List Tickets
# ========================
@router.get("/", response_model=list[TicketOut])
def list_tickets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role in ["admin", "provider", "service_provider"]:
        return db.query(Ticket).filter(
            Ticket.tenant_id == current_user.tenant_id
        ).all()

    return db.query(Ticket).filter(
        Ticket.created_by_user_id == current_user.id
    ).all()


# ========================
# Update Ticket Status
# ========================
@router.put("/{ticket_id}/status")
def update_status(
    ticket_id: int,
    status: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    allowed_status = ["open", "in-progress", "resolved", "closed"]
    if status not in allowed_status:
        raise HTTPException(status_code=400, detail="Invalid status value")

    ticket.status = status
    db.commit()
    db.refresh(ticket)

    return {"message": "Status updated successfully", "ticket": ticket}


# ========================
# Admin Assign Ticket
# ========================
@router.put("/{ticket_id}/assign/{user_id}")
def assign_ticket(
    ticket_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can assign tickets")

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant assignment not allowed")

    if user.role not in ["provider", "service_provider"]:
        raise HTTPException(status_code=400, detail="User is not a provider")

    ticket.assigned_to_user_id = user_id
    db.commit()
    db.refresh(ticket)

    return {"message": "Ticket assigned successfully", "ticket": ticket}


# ========================
# Tenant Tickets
# ========================
@router.get("/tenant/{tenant_id}", response_model=list[TicketOut])
def get_tenant_tickets(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    tickets = db.query(Ticket).filter(Ticket.tenant_id == tenant_id).all()

    if not tickets:
        raise HTTPException(status_code=404, detail="No tickets found")

    return tickets


# ========================
# Provider My Tickets
# ========================
@router.get("/provider/my-tickets", response_model=list[TicketOut])
def provider_my_tickets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in ["provider", "service_provider"]:
        raise HTTPException(status_code=403, detail="Only providers allowed")

    return db.query(Ticket).filter(
        Ticket.assigned_to_user_id == current_user.id
    ).all()


# ========================
# Provider Update Status
# ========================
@router.put("/provider/{ticket_id}/status")
def provider_update_status(
    ticket_id: int,
    status: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in ["provider", "service_provider"]:
        raise HTTPException(status_code=403, detail="Only providers allowed")

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket.assigned_to_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your ticket")

    allowed = ["in-progress", "resolved", "closed"]
    if status not in allowed:
        raise HTTPException(status_code=400, detail=f"Allowed: {allowed}")

    ticket.status = status
    db.commit()
    db.refresh(ticket)

    return {"message": "Status updated", "ticket": ticket}


# ========================
# Customer My Tickets
# ========================
@router.get("/customer/my-tickets", response_model=list[TicketOut])
def customer_my_tickets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "customer":
        raise HTTPException(status_code=403, detail="Only customers allowed")

    return db.query(Ticket).filter(
        Ticket.created_by_user_id == current_user.id
    ).all()


# ========================
# Admin SLA Check
# ========================
@router.post("/admin/run-sla-check")
def run_sla_check(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admins only")

    escalated_count = check_and_escalate_sla(db)

    return {
        "message": "SLA check completed",
        "tickets_escalated": escalated_count
    }

@router.post("/ai-create", response_model=TicketOut)
def ai_create_ticket(
    text: str = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    tenant_id = current_user.tenant_id

    title = text[:40] + "..."
    priority = predict_priority(text)
    category = predict_category(text, text)

    new_ticket = Ticket(
        title=title,
        description=text,
        priority=priority,
        category=category,
        tenant_id=tenant_id,
        created_by_user_id=current_user.id
    )

    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)

    return new_ticket
