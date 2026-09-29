"""
ORM models. A "tenant" is an organization: every org-owned row carries
`tenant_id`, and every query that reads or writes org data filters on it.

Timestamps use UTCDateTime (aware UTC everywhere). `data_origin` marks rows as
`real`, `demo` or `synthetic` so analytics never mix demo data into
production metrics without saying so.
"""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.db.database import Base, UTCDateTime, utcnow

JSONType = JSON().with_variant(JSONB(), "postgresql")


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    slug = Column(String(80), nullable=False, unique=True, index=True)
    domain = Column(String(255), nullable=True, unique=True, index=True)
    is_demo = Column(Boolean, nullable=False, default=False)
    settings = Column(JSONType, nullable=False, default=dict)
    # Per-organization ticket counter backing Ticket.number (#1, #2, ...).
    ticket_seq = Column(Integer, nullable=False, default=0)
    data_origin = Column(String(16), nullable=False, default="real")
    created_at = Column(UTCDateTime, nullable=False, default=utcnow)

    users = relationship("User", back_populates="tenant")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    email = Column(String(255), nullable=False, unique=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False)
    # NULL only for platform administrators, who belong to no organization.
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    email_verified_at = Column(UTCDateTime, nullable=True)
    last_login_at = Column(UTCDateTime, nullable=True)
    data_origin = Column(String(16), nullable=False, default="real")
    created_at = Column(UTCDateTime, nullable=False, default=utcnow)

    tenant = relationship("Tenant", back_populates="users")
    teams = relationship("Team", secondary="team_members", back_populates="members")


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_teams_tenant_name"),)

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(80), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(UTCDateTime, nullable=False, default=utcnow)

    members = relationship("User", secondary="team_members", back_populates="teams")


class TeamMember(Base):
    __tablename__ = "team_members"

    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    created_at = Column(UTCDateTime, nullable=False, default=utcnow)


class Category(Base):
    """An org's ticket taxonomy. `keywords` drive the deterministic rules
    engine; `default_team_id` is the routing rule used by triage when no model
    or human has picked a team."""

    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_categories_tenant_name"),)

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(80), nullable=False)
    description = Column(Text, nullable=True)
    keywords = Column(JSONType, nullable=False, default=list)
    default_team_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    default_team = relationship("Team")


class SlaPolicy(Base):
    __tablename__ = "sla_policies"
    __table_args__ = (UniqueConstraint("tenant_id", "priority", name="uq_sla_policies_tenant_priority"),)

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    priority = Column(String(16), nullable=False)
    first_response_minutes = Column(Integer, nullable=False)
    resolution_minutes = Column(Integer, nullable=False)


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_tickets_tenant_number"),
        Index("ix_tickets_tenant_status", "tenant_id", "status"),
        Index("ix_tickets_tenant_assignee", "tenant_id", "assigned_to_user_id"),
        Index("ix_tickets_tenant_requester", "tenant_id", "created_by_user_id"),
        Index("ix_tickets_tenant_created", "tenant_id", "created_at"),
        Index("ix_tickets_tenant_team", "tenant_id", "team_id"),
        Index("ix_tickets_resolution_due", "resolution_due"),
    )

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    number = Column(Integer, nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    priority = Column(String(16), nullable=False)
    category = Column(String(80), nullable=True)
    status = Column(String(32), nullable=False)
    channel = Column(String(16), nullable=False, default="web")

    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    # Who produced the current category/priority/team: rules | manual | ai.
    triage_source = Column(String(16), nullable=True)

    first_response_due = Column(UTCDateTime, nullable=True)
    first_responded_at = Column(UTCDateTime, nullable=True)
    first_response_breached_at = Column(UTCDateTime, nullable=True)
    resolution_due = Column(UTCDateTime, nullable=True)
    resolution_breached_at = Column(UTCDateTime, nullable=True)
    # Set while the ticket waits on the customer; the resolution clock is
    # shifted forward by the paused duration when work resumes.
    sla_paused_at = Column(UTCDateTime, nullable=True)

    acknowledged_at = Column(UTCDateTime, nullable=True)
    resolved_at = Column(UTCDateTime, nullable=True)
    closed_at = Column(UTCDateTime, nullable=True)
    reopened_count = Column(Integer, nullable=False, default=0)
    resolution_summary = Column(Text, nullable=True)

    data_origin = Column(String(16), nullable=False, default="real")
    created_at = Column(UTCDateTime, nullable=False, default=utcnow)
    updated_at = Column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)

    requester = relationship("User", foreign_keys=[created_by_user_id])
    assignee = relationship("User", foreign_keys=[assigned_to_user_id])
    team = relationship("Team")


class TicketStatusHistory(Base):
    __tablename__ = "ticket_status_history"
    __table_args__ = (Index("ix_status_history_ticket_created", "ticket_id", "created_at"),)

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    from_status = Column(String(32), nullable=True)
    to_status = Column(String(32), nullable=False)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # user | system | ai
    actor_type = Column(String(16), nullable=False)
    reason = Column(Text, nullable=True)
    created_at = Column(UTCDateTime, nullable=False, default=utcnow)

    actor = relationship("User")


class TicketComment(Base):
    __tablename__ = "ticket_comments"
    __table_args__ = (Index("ix_comments_ticket_created", "ticket_id", "created_at"),)

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    # Nullable only for rows written before comments had authors.
    author_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # public: visible to the requester · internal: staff-only note
    visibility = Column(String(16), nullable=False, default="public")
    content = Column(Text, nullable=False)
    created_at = Column(UTCDateTime, nullable=False, default=utcnow)

    author = relationship("User")


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    comment_id = Column(Integer, ForeignKey("ticket_comments.id", ondelete="CASCADE"), nullable=True)
    uploaded_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    storage_key = Column(String(255), nullable=False, unique=True)
    created_at = Column(UTCDateTime, nullable=False, default=utcnow)

    uploaded_by = relationship("User")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_read", "user_id", "is_read"),)

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=True)
    link = Column(String(255), nullable=True)
    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(UTCDateTime, nullable=False, default=utcnow)


class Invitation(Base):
    __tablename__ = "invitations"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)
    role = Column(String(32), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    token_hash = Column(String(64), nullable=False, unique=True)
    invited_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    expires_at = Column(UTCDateTime, nullable=False)
    accepted_at = Column(UTCDateTime, nullable=True)
    revoked_at = Column(UTCDateTime, nullable=True)
    created_at = Column(UTCDateTime, nullable=False, default=utcnow)

    tenant = relationship("Tenant")
    invited_by = relationship("User")


class UserToken(Base):
    """Single-use tokens for email verification and password reset. Only a
    SHA-256 hash is stored; the raw token exists only in the emailed link."""

    __tablename__ = "user_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    purpose = Column(String(32), nullable=False)  # email_verification | password_reset
    token_hash = Column(String(64), nullable=False, unique=True)
    expires_at = Column(UTCDateTime, nullable=False)
    used_at = Column(UTCDateTime, nullable=True)
    created_at = Column(UTCDateTime, nullable=False, default=utcnow)


class RefreshToken(Base):
    """Rotating refresh tokens. Each refresh replaces the token; presenting an
    already-rotated token revokes its whole family (token-theft signal)."""

    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    family_id = Column(String(36), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True)
    expires_at = Column(UTCDateTime, nullable=False)
    rotated_at = Column(UTCDateTime, nullable=True)
    revoked_at = Column(UTCDateTime, nullable=True)
    user_agent = Column(String(255), nullable=True)
    ip = Column(String(64), nullable=True)
    created_at = Column(UTCDateTime, nullable=False, default=utcnow)


class AuditLog(Base):
    """Append-only record of security- and business-relevant actions."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_tenant_created", "tenant_id", "created_at"),
        Index("ix_audit_entity", "entity_type", "entity_id"),
    )

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    actor_type = Column(String(16), nullable=False)  # user | system | ai | anonymous
    action = Column(String(64), nullable=False)
    entity_type = Column(String(32), nullable=True)
    entity_id = Column(String(64), nullable=True)
    changes = Column(JSONType, nullable=True)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(255), nullable=True)
    request_id = Column(String(64), nullable=True)
    created_at = Column(UTCDateTime, nullable=False, default=utcnow)

    actor = relationship("User")


class EmailOutbox(Base):
    """Every outgoing email is written here first (transactional outbox), then
    delivered by the configured backend. Gives a durable record and a retry
    point, and lets local development read emails without an SMTP server."""

    __tablename__ = "email_outbox"
    __table_args__ = (Index("ix_email_outbox_status_created", "status", "created_at"),)

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    to_email = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=False)
    body_text = Column(Text, nullable=False)
    template = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, default="queued")  # queued | sent | failed
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(UTCDateTime, nullable=False, default=utcnow)
    sent_at = Column(UTCDateTime, nullable=True)
