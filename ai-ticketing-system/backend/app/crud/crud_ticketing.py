# backend/app/crud/crud_ticketing.py
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.models.models import Tenant, User, Ticket, TicketComment
from app.schemas.schemas import (
    TenantCreate, UserCreate, TicketCreate, TicketUpdate,
    TicketCommentCreate
)

# ---------------- Tenant CRUD ----------------
def create_tenant(db: Session, tenant: TenantCreate) -> Tenant:
    db_tenant = Tenant(name=tenant.name, domain=tenant.domain)
    db.add(db_tenant)
    db.commit()
    db.refresh(db_tenant)
    return db_tenant


def get_tenant(db: Session, tenant_id: int) -> Optional[Tenant]:
    return db.query(Tenant).filter(Tenant.id == tenant_id).first()


def get_all_tenants(db: Session) -> List[Tenant]:
    return db.query(Tenant).all()


# ---------------- User CRUD ----------------
def create_user(db: Session, user: UserCreate, tenant_id: int, hashed_password: str) -> User:
    db_user = User(
        name=user.name,
        email=user.email,
        role=user.role,
        tenant_id=tenant_id,
        hashed_password=hashed_password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_user(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()


# ---------------- Ticket CRUD ----------------
def create_ticket(db: Session, ticket: TicketCreate, user_id: int, tenant_id: int) -> Ticket:
    db_ticket = Ticket(
        title=ticket.title,
        description=ticket.description,
        priority=ticket.priority,
        status=ticket.status or "open",
        created_by_user_id=user_id,
        tenant_id=tenant_id
    )
    db.add(db_ticket)
    db.commit()
    db.refresh(db_ticket)
    return db_ticket


def get_ticket(db: Session, ticket_id: int) -> Optional[Ticket]:
    return db.query(Ticket).filter(Ticket.id == ticket_id).first()


def get_all_tickets(db: Session, tenant_id: Optional[int] = None) -> List[Ticket]:
    query = db.query(Ticket)
    if tenant_id:
        query = query.filter(Ticket.tenant_id == tenant_id)
    return query.all()


def update_ticket(db: Session, ticket_id: int, ticket_update: TicketUpdate) -> Optional[Ticket]:
    db_ticket = get_ticket(db, ticket_id)
    if not db_ticket:
        return None
    for key, value in ticket_update.dict(exclude_unset=True).items():
        setattr(db_ticket, key, value)
    db.commit()
    db.refresh(db_ticket)
    return db_ticket


# ---------------- Ticket Comment CRUD ----------------
def add_ticket_comment(db: Session, ticket_id: int, comment: TicketCommentCreate) -> TicketComment:
    db_comment = TicketComment(
        content=comment.content,
        ticket_id=ticket_id
    )
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    return db_comment


def get_ticket_comments(db: Session, ticket_id: int) -> List[TicketComment]:
    return db.query(TicketComment).filter(TicketComment.ticket_id == ticket_id).all()
