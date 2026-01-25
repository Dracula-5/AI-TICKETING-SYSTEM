from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    domain = Column(String, unique=True, index=True)

    users = relationship("User", back_populates="tenant")
    tickets = relationship("Ticket", back_populates="tenant")
    providers = relationship("Provider", back_populates="tenant")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String)      # admin / provider / customer / service_provider
    tenant_id = Column(Integer, ForeignKey("tenants.id"))

    tenant = relationship("Tenant", back_populates="users")

    tickets = relationship(
        "Ticket",
        back_populates="created_by_user",
        foreign_keys="Ticket.created_by_user_id"
    )


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    priority = Column(String, nullable=False)

    category = Column(String, nullable=True)

    status = Column(String, default="open")
    created_at = Column(DateTime, default=datetime.utcnow)

    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    created_by_user_id = Column(Integer, ForeignKey("users.id"))
    assigned_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    sla_due = Column(DateTime, nullable=True)
    is_escalated = Column(Boolean, default=False)

    tenant = relationship("Tenant", back_populates="tickets")

    created_by_user = relationship(
        "User",
        foreign_keys=[created_by_user_id]
    )

    assigned_user = relationship(
        "User",
        foreign_keys=[assigned_to_user_id]
    )

    comments = relationship(
        "TicketComment",
        back_populates="ticket",
        cascade="all, delete"
    )


class TicketComment(Base):
    __tablename__ = "ticket_comments"

    id = Column(Integer, primary_key=True)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    ticket_id = Column(Integer, ForeignKey("tickets.id"))

    ticket = relationship("Ticket", back_populates="comments")


class Provider(Base):
    __tablename__ = "providers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    department = Column(String, nullable=True)
    contact = Column(String, nullable=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"))

    tenant = relationship("Tenant", back_populates="providers")
