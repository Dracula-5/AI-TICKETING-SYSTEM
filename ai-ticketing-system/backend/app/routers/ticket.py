from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.db.database import get_db
from app.db.models import Ticket, User, PriceNegotiation
from app.schemas.tickets import (
    TicketCreate,
    TicketOut,
    BargainingOfferIn,
    BargainingActionIn,
    BargainingEntryOut,
    BargainingMonitorOut,
    BargainingActionOut,
)
from app.core.security import get_current_user

from app.services.auto_router import predict_category
from app.ai.priority import predict_priority
from app.services.sla_checker import check_and_escalate_sla
from fastapi import Body


router = APIRouter(
    prefix="/tickets",
    tags=["tickets"]
)

PROVIDER_ROLES = ["provider", "service_provider"]


def _is_provider(user: User) -> bool:
    return user.role in PROVIDER_ROLES


def _load_ticket_for_tenant(ticket_id: int, db: Session, current_user: User) -> Ticket:
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return ticket


def _load_latest_proposal(db: Session, ticket_id: int) -> PriceNegotiation | None:
    return (
        db.query(PriceNegotiation)
        .filter(
            PriceNegotiation.ticket_id == ticket_id,
            PriceNegotiation.action.in_(["offer", "counter"]),
        )
        .order_by(PriceNegotiation.created_at.desc(), PriceNegotiation.id.desc())
        .first()
    )


def _load_target_offer(db: Session, ticket_id: int, negotiation_id: int | None) -> PriceNegotiation | None:
    if negotiation_id is not None:
        return (
            db.query(PriceNegotiation)
            .filter(
                PriceNegotiation.ticket_id == ticket_id,
                PriceNegotiation.id == negotiation_id,
                PriceNegotiation.action.in_(["offer", "counter"]),
            )
            .first()
        )
    return _load_latest_proposal(db, ticket_id)


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
    if priority == "critical":
        sla_hours = 2
    elif priority == "high":
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

    allowed_status = ["open", "negotiating", "in-progress", "resolved", "closed"]
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

@router.get("/provider/open", response_model=list[TicketOut])
def provider_open_tickets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in PROVIDER_ROLES:
        raise HTTPException(status_code=403, detail="Only providers allowed")

    return db.query(Ticket).filter(
        Ticket.tenant_id == current_user.tenant_id,
        Ticket.assigned_to_user_id == None,  # noqa: E711
        Ticket.status == "open"
    ).all()

@router.post("/provider/offer/{ticket_id}")
def provider_offer_help(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in PROVIDER_ROLES:
        raise HTTPException(status_code=403, detail="Only providers allowed")

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    if ticket.assigned_to_user_id is not None:
        raise HTTPException(status_code=400, detail="Ticket already assigned")

    if ticket.status != "open":
        raise HTTPException(status_code=400, detail="Ticket is not open")

    ticket.assigned_to_user_id = current_user.id
    ticket.status = "negotiating"
    if ticket.pricing_status == "pending":
        ticket.pricing_status = "negotiating"
    db.commit()
    db.refresh(ticket)

    return {"message": "You are now assigned. Finalize cost with customer before starting work.", "ticket": ticket}


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
    if current_user.role not in PROVIDER_ROLES:
        raise HTTPException(status_code=403, detail="Only providers allowed")

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket.assigned_to_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your ticket")

    allowed = ["negotiating", "in-progress", "resolved", "closed"]
    if status not in allowed:
        raise HTTPException(status_code=400, detail=f"Allowed: {allowed}")

    if status in ["in-progress", "resolved", "closed"] and ticket.pricing_status != "finalized":
        raise HTTPException(
            status_code=400,
            detail="Finalize bargaining price before accepting or closing this ticket"
        )

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


@router.get("/{ticket_id}/bargaining", response_model=list[BargainingEntryOut])
def get_bargaining_history(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _load_ticket_for_tenant(ticket_id, db, current_user)
    return (
        db.query(PriceNegotiation)
        .filter(PriceNegotiation.ticket_id == ticket_id)
        .order_by(PriceNegotiation.created_at.asc(), PriceNegotiation.id.asc())
        .all()
    )


@router.post("/{ticket_id}/bargaining/offer", response_model=BargainingActionOut, status_code=status.HTTP_201_CREATED)
def create_bargaining_offer(
    ticket_id: int,
    payload: BargainingOfferIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = _load_ticket_for_tenant(ticket_id, db, current_user)

    if ticket.pricing_status == "finalized":
        raise HTTPException(status_code=400, detail="Price already finalized for this ticket")

    if current_user.role == "customer":
        if ticket.created_by_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Only ticket owner can bargain as customer")
        if ticket.assigned_to_user_id is None:
            raise HTTPException(status_code=400, detail="Wait for a provider to pick the ticket first")
    elif _is_provider(current_user):
        if ticket.assigned_to_user_id is None:
            ticket.assigned_to_user_id = current_user.id
        elif ticket.assigned_to_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Only assigned provider can bargain on this ticket")
    else:
        raise HTTPException(status_code=403, detail="Only customer/provider can bargain")

    action = "counter" if _load_latest_proposal(db, ticket_id) else "offer"
    sender_role = "provider" if _is_provider(current_user) else "customer"

    entry = PriceNegotiation(
        ticket_id=ticket.id,
        sender_user_id=current_user.id,
        sender_role=sender_role,
        action=action,
        amount=payload.amount,
        message=payload.message,
        is_final=False,
    )
    ticket.pricing_status = "negotiating"
    ticket.status = "negotiating" if ticket.status == "open" else ticket.status

    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {
        "message": f"Budget/offer submitted at Rs {entry.amount}",
        "pricing_status": ticket.pricing_status,
        "final_price": ticket.final_price,
        "negotiation": entry,
    }


@router.post("/{ticket_id}/bargaining/accept", response_model=BargainingActionOut)
def accept_bargaining_offer(
    ticket_id: int,
    payload: BargainingActionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = _load_ticket_for_tenant(ticket_id, db, current_user)
    if ticket.pricing_status == "finalized":
        raise HTTPException(
            status_code=400,
            detail=f"Deal already finalized at Rs {ticket.final_price}"
        )

    if current_user.role == "customer":
        if ticket.created_by_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Only ticket owner can accept as customer")
    elif _is_provider(current_user):
        if ticket.assigned_to_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Only assigned provider can accept for this ticket")
    else:
        raise HTTPException(status_code=403, detail="Only customer/provider can accept bargain")

    latest_offer = _load_target_offer(db, ticket_id, payload.negotiation_id)
    if not latest_offer:
        raise HTTPException(status_code=400, detail="Selected offer not found")

    latest_open_offer = _load_latest_proposal(db, ticket_id)
    if not latest_open_offer or latest_open_offer.id != latest_offer.id:
        raise HTTPException(
            status_code=409,
            detail="Selected offer is stale. Another update happened. Please refresh and use the latest offer."
        )

    if latest_offer.sender_user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot accept your own offer")

    sender_role = "provider" if _is_provider(current_user) else "customer"
    entry = PriceNegotiation(
        ticket_id=ticket.id,
        sender_user_id=current_user.id,
        sender_role=sender_role,
        action="accept",
        amount=latest_offer.amount,
        message=payload.message,
        is_final=True,
    )

    ticket.final_price = latest_offer.amount
    ticket.pricing_status = "finalized"
    ticket.price_finalized_at = datetime.utcnow()
    ticket.status = "in-progress"

    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {
        "message": f"Deal finalized at Rs {latest_offer.amount}",
        "pricing_status": ticket.pricing_status,
        "final_price": ticket.final_price,
        "negotiation": entry,
    }


@router.post("/{ticket_id}/bargaining/reject", response_model=BargainingActionOut)
def reject_bargaining_offer(
    ticket_id: int,
    payload: BargainingActionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = _load_ticket_for_tenant(ticket_id, db, current_user)
    if ticket.pricing_status == "finalized":
        raise HTTPException(
            status_code=400,
            detail=f"Deal already finalized at Rs {ticket.final_price}"
        )

    if current_user.role == "customer":
        if ticket.created_by_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Only ticket owner can reject as customer")
    elif _is_provider(current_user):
        if ticket.assigned_to_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Only assigned provider can reject for this ticket")
    else:
        raise HTTPException(status_code=403, detail="Only customer/provider can reject bargain")

    latest_offer = _load_target_offer(db, ticket_id, payload.negotiation_id)
    if not latest_offer:
        raise HTTPException(status_code=400, detail="Selected offer not found")

    latest_open_offer = _load_latest_proposal(db, ticket_id)
    if not latest_open_offer or latest_open_offer.id != latest_offer.id:
        raise HTTPException(
            status_code=409,
            detail="Selected offer is stale. Another update happened. Please refresh and use the latest offer."
        )

    if latest_offer.sender_user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot reject your own offer")

    sender_role = "provider" if _is_provider(current_user) else "customer"
    entry = PriceNegotiation(
        ticket_id=ticket.id,
        sender_user_id=current_user.id,
        sender_role=sender_role,
        action="reject",
        amount=latest_offer.amount,
        message=payload.message,
        is_final=False,
    )
    ticket.pricing_status = "negotiating"
    ticket.status = "negotiating"

    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {
        "message": f"Offer at Rs {latest_offer.amount} rejected. Share your budget/counter.",
        "pricing_status": ticket.pricing_status,
        "final_price": ticket.final_price,
        "negotiation": entry,
    }


@router.get("/bargaining/monitor", response_model=list[BargainingMonitorOut])
def admin_bargaining_monitor(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admins only")

    tickets = (
        db.query(Ticket)
        .filter(Ticket.tenant_id == current_user.tenant_id)
        .order_by(Ticket.updated_at.desc())
        .all()
    )

    monitor_rows: list[BargainingMonitorOut] = []
    for ticket in tickets:
        last_entry = (
            db.query(PriceNegotiation)
            .filter(PriceNegotiation.ticket_id == ticket.id)
            .order_by(PriceNegotiation.created_at.desc(), PriceNegotiation.id.desc())
            .first()
        )
        if not last_entry and ticket.pricing_status == "pending":
            continue

        monitor_rows.append(
            BargainingMonitorOut(
                ticket_id=ticket.id,
                ticket_title=ticket.title,
                ticket_status=ticket.status,
                pricing_status=ticket.pricing_status,
                final_price=ticket.final_price,
                last_action=last_entry.action if last_entry else None,
                last_amount=last_entry.amount if last_entry else None,
                last_sender_role=last_entry.sender_role if last_entry else None,
                last_created_at=last_entry.created_at if last_entry else None,
            )
        )

    return monitor_rows

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

    if priority == "critical":
        sla_hours = 2
    elif priority == "high":
        sla_hours = 6
    elif priority == "medium":
        sla_hours = 12
    else:
        sla_hours = 24

    sla_due_time = datetime.utcnow() + timedelta(hours=sla_hours)

    new_ticket = Ticket(
        title=title,
        description=text,
        priority=priority,
        category=category,
        tenant_id=tenant_id,
        created_by_user_id=current_user.id,
        sla_due=sla_due_time
    )

    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)

    return new_ticket
