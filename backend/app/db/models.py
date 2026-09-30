"""
ORM models. A "tenant" is an organization: every org-owned row carries
`tenant_id`, and every query that reads or writes org data filters on it.

Timestamps use UTCDateTime (aware UTC everywhere). `data_origin` marks rows as
`real`, `demo` or `synthetic` so analytics never mix demo data into
production metrics without saying so.

Declared with SQLAlchemy 2 typed mappings (Mapped[...]) so attribute types are
checked statically; tests/test_migrations.py proves the Alembic chain builds
exactly this schema.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import EMBEDDING_DIM, Base, EmbeddingVector, UTCDateTime, utcnow

JSONType = JSON().with_variant(JSONB(), "postgresql")


def _fk(target: str, ondelete: str | None = None) -> ForeignKey:
    return ForeignKey(target, ondelete=ondelete)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    domain: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    is_demo: Mapped[bool] = mapped_column(default=False)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    # Per-organization ticket counter backing Ticket.number (#1, #2, ...).
    ticket_seq: Mapped[int] = mapped_column(default=0)
    data_origin: Mapped[str] = mapped_column(String(16), default="real")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="tenant")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32))
    # NULL only for platform administrators, who belong to no organization.
    tenant_id: Mapped[int | None] = mapped_column(_fk("tenants.id"), index=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    data_origin: Mapped[str] = mapped_column(String(16), default="real")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    tenant: Mapped[Tenant | None] = relationship(back_populates="users")
    teams: Mapped[list["Team"]] = relationship(secondary="team_members", back_populates="members")


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_teams_tenant_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(_fk("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    members: Mapped[list[User]] = relationship(secondary="team_members", back_populates="teams")


class TeamMember(Base):
    __tablename__ = "team_members"

    team_id: Mapped[int] = mapped_column(_fk("teams.id", "CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(_fk("users.id", "CASCADE"), primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Category(Base):
    """An org's ticket taxonomy. `keywords` drive the deterministic rules
    engine; `default_team_id` is the routing rule used by triage when no model
    or human has picked a team."""

    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_categories_tenant_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(_fk("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(JSONType, default=list)
    default_team_id: Mapped[int | None] = mapped_column(_fk("teams.id", "SET NULL"))
    is_active: Mapped[bool] = mapped_column(default=True)

    default_team: Mapped[Team | None] = relationship()


class SlaPolicy(Base):
    __tablename__ = "sla_policies"
    __table_args__ = (UniqueConstraint("tenant_id", "priority", name="uq_sla_policies_tenant_priority"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(_fk("tenants.id"), index=True)
    priority: Mapped[str] = mapped_column(String(16))
    first_response_minutes: Mapped[int]
    resolution_minutes: Mapped[int]


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

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(_fk("tenants.id"))
    number: Mapped[int]
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(16))
    category: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32))
    channel: Mapped[str] = mapped_column(String(16), default="web")

    created_by_user_id: Mapped[int] = mapped_column(_fk("users.id"))
    assigned_to_user_id: Mapped[int | None] = mapped_column(_fk("users.id"))
    team_id: Mapped[int | None] = mapped_column(_fk("teams.id", "SET NULL"))
    # Who produced the current category/priority/team: rules | manual | ai.
    triage_source: Mapped[str | None] = mapped_column(String(16))

    first_response_due: Mapped[datetime | None] = mapped_column(UTCDateTime)
    first_responded_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    first_response_breached_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    resolution_due: Mapped[datetime | None] = mapped_column(UTCDateTime)
    resolution_breached_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Set while the ticket waits on the customer; the resolution clock is
    # shifted forward by the paused duration when work resumes.
    sla_paused_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    reopened_count: Mapped[int] = mapped_column(default=0)
    resolution_summary: Mapped[str | None] = mapped_column(Text)

    data_origin: Mapped[str] = mapped_column(String(16), default="real")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    tenant: Mapped[Tenant] = relationship()
    requester: Mapped[User] = relationship(foreign_keys=[created_by_user_id])
    assignee: Mapped[User | None] = relationship(foreign_keys=[assigned_to_user_id])
    team: Mapped[Team | None] = relationship()


class TicketStatusHistory(Base):
    __tablename__ = "ticket_status_history"
    __table_args__ = (Index("ix_status_history_ticket_created", "ticket_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(_fk("tenants.id"), index=True)
    ticket_id: Mapped[int] = mapped_column(_fk("tickets.id", "CASCADE"))
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    actor_user_id: Mapped[int | None] = mapped_column(_fk("users.id"))
    # user | system | ai
    actor_type: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    actor: Mapped[User | None] = relationship()


class TicketComment(Base):
    __tablename__ = "ticket_comments"
    __table_args__ = (Index("ix_comments_ticket_created", "ticket_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(_fk("tenants.id"), index=True)
    ticket_id: Mapped[int] = mapped_column(_fk("tickets.id", "CASCADE"))
    # Nullable only for rows written before comments had authors.
    author_user_id: Mapped[int | None] = mapped_column(_fk("users.id"))
    # public: visible to the requester · internal: staff-only note
    visibility: Mapped[str] = mapped_column(String(16), default="public")
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    author: Mapped[User | None] = relationship()


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(_fk("tenants.id"), index=True)
    ticket_id: Mapped[int] = mapped_column(_fk("tickets.id", "CASCADE"), index=True)
    comment_id: Mapped[int | None] = mapped_column(_fk("ticket_comments.id", "CASCADE"))
    uploaded_by_user_id: Mapped[int] = mapped_column(_fk("users.id"))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    uploaded_by: Mapped[User] = relationship()


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_read", "user_id", "is_read"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(_fk("tenants.id"), index=True)
    user_id: Mapped[int] = mapped_column(_fk("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(255))
    is_read: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(_fk("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(32))
    team_id: Mapped[int | None] = mapped_column(_fk("teams.id", "SET NULL"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by_user_id: Mapped[int] = mapped_column(_fk("users.id"))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    tenant: Mapped[Tenant] = relationship()
    invited_by: Mapped[User] = relationship()


class UserToken(Base):
    """Single-use tokens for email verification and password reset. Only a
    SHA-256 hash is stored; the raw token exists only in the emailed link."""

    __tablename__ = "user_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(_fk("users.id", "CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(32))  # email_verification | password_reset
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class RefreshToken(Base):
    """Rotating refresh tokens. Each refresh replaces the token; presenting an
    already-rotated token revokes its whole family (token-theft signal)."""

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(_fk("users.id", "CASCADE"), index=True)
    family_id: Mapped[str] = mapped_column(String(36), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    rotated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AuditLog(Base):
    """Append-only record of security- and business-relevant actions."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_tenant_created", "tenant_id", "created_at"),
        Index("ix_audit_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(_fk("tenants.id"))
    actor_user_id: Mapped[int | None] = mapped_column(_fk("users.id"))
    actor_type: Mapped[str] = mapped_column(String(16))  # user | system | ai | anonymous
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    actor: Mapped[User | None] = relationship()


class EmailOutbox(Base):
    """Every outgoing email is written here first (transactional outbox), then
    delivered by the configured backend. Gives a durable record and a retry
    point, and lets local development read emails without an SMTP server."""

    __tablename__ = "email_outbox"
    __table_args__ = (Index("ix_email_outbox_status_created", "status", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(_fk("tenants.id"))
    to_email: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    body_text: Mapped[str] = mapped_column(Text)
    template: Mapped[str] = mapped_column(String(64))
    # queued | sent | failed (retry scheduled) | dead (gave up — dead letter)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Job(Base):
    """Background job queue (services/jobs.py): transactional enqueue, SKIP LOCKED
    claiming, retry with backoff, lease-based recovery, dead letter."""

    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status_run_after", "status", "run_after"),
        Index("ix_jobs_dedupe_key", "dedupe_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(_fk("tenants.id"))
    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    dedupe_key: Mapped[str | None] = mapped_column(String(128))
    # queued | running | done | failed (retry scheduled) | dead
    status: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=5)
    run_after: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    duration_ms: Mapped[float | None]
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AIPrediction(Base):
    """One AI (or rules) recommendation for a ticket and what a human did with
    it. The source of every AI-performance metric: acceptance, edit and
    rejection rates, auto-apply rate, latency and model versions."""

    __tablename__ = "ai_predictions"
    __table_args__ = (
        Index("ix_ai_predictions_ticket_kind", "ticket_id", "kind"),
        Index("ix_ai_predictions_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(_fk("tenants.id"))
    ticket_id: Mapped[int] = mapped_column(_fk("tickets.id", "CASCADE"))
    # category | priority | team | assignee | duplicate | sla_risk | summary | reply | next_action
    kind: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(16))  # ai | rules
    model: Mapped[str] = mapped_column(String(128))
    model_version: Mapped[str] = mapped_column(String(64))
    value: Mapped[dict[str, Any]] = mapped_column(JSONType)
    confidence: Mapped[float | None]
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    latency_ms: Mapped[float | None]
    # proposed | auto_applied | accepted | edited | rejected | superseded | overridden
    # | no_change (already true) | invalid (failed validation) | failed_verification
    status: Mapped[str] = mapped_column(String(24), default="proposed")
    final_value: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    decided_by_user_id: Mapped[int | None] = mapped_column(_fk("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    input_sha256: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class LLMCall(Base):
    """Ledger of every call to a text-generation provider: what feature, which
    model, tokens, latency, outcome and (when prices are configured) cost."""

    __tablename__ = "llm_calls"
    __table_args__ = (Index("ix_llm_calls_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(_fk("tenants.id"))
    ticket_id: Mapped[int | None] = mapped_column(_fk("tickets.id", "SET NULL"))
    user_id: Mapped[int | None] = mapped_column(_fk("users.id", "SET NULL"))
    feature: Mapped[str] = mapped_column(String(32))  # summary | reply | ...
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok | empty | error
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cost_usd: Mapped[float | None]
    latency_ms: Mapped[float | None]
    error: Mapped[str | None] = mapped_column(String(500))
    prompt_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class TicketEmbedding(Base):
    """Semantic vector of a ticket's text (pgvector on PostgreSQL). Queried
    only with a tenant_id filter in the same SQL statement, so similarity
    search can never cross organizations."""

    __tablename__ = "ticket_embeddings"
    __table_args__ = (Index("ix_ticket_embeddings_tenant", "tenant_id"),)

    ticket_id: Mapped[int] = mapped_column(_fk("tickets.id", "CASCADE"), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(_fk("tenants.id"))
    model: Mapped[str] = mapped_column(String(128))
    embedding: Mapped[Any] = mapped_column(EmbeddingVector(EMBEDDING_DIM))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class KBDocument(Base):
    """A knowledge-base document of one organization. `public` documents are
    searchable by requesters in the portal; `internal` ones only by staff."""

    __tablename__ = "kb_documents"
    __table_args__ = (Index("ix_kb_documents_tenant", "tenant_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(_fk("tenants.id"))
    title: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    visibility: Mapped[str] = mapped_column(String(16), default="internal")  # internal | public
    status: Mapped[str] = mapped_column(String(16), default="processing")  # processing | ready | failed
    error: Mapped[str | None] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int]
    chunk_count: Mapped[int] = mapped_column(default=0)
    # Extracted plain text (source for re-chunking / re-embedding without the file).
    text: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(_fk("users.id", "SET NULL"))
    data_origin: Mapped[str] = mapped_column(String(16), default="real")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class KBChunk(Base):
    """A retrievable passage. PostgreSQL adds a generated `tsv` column with a GIN
    index and an HNSW index on `embedding` (migration 0005)."""

    __tablename__ = "kb_chunks"
    __table_args__ = (Index("ix_kb_chunks_tenant_doc", "tenant_id", "document_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(_fk("tenants.id"))
    document_id: Mapped[int] = mapped_column(_fk("kb_documents.id", "CASCADE"))
    ordinal: Mapped[int]
    heading: Mapped[str | None] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    visibility: Mapped[str] = mapped_column(String(16), default="internal")
    model: Mapped[str] = mapped_column(String(128))
    embedding: Mapped[Any] = mapped_column(EmbeddingVector(EMBEDDING_DIM))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class KBQuery(Base):
    """One knowledge-base search or question: what was asked, what came back,
    whether an answer was given and whether the asker found it helpful. Source
    of retrieval/answer telemetry and, with real users, deflection metrics."""

    __tablename__ = "kb_queries"
    __table_args__ = (Index("ix_kb_queries_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(_fk("tenants.id"))
    user_id: Mapped[int | None] = mapped_column(_fk("users.id", "SET NULL"))
    mode: Mapped[str] = mapped_column(String(16))  # search | answer
    query: Mapped[str] = mapped_column(Text)
    retrieval_mode: Mapped[str] = mapped_column(String(32))
    results: Mapped[int] = mapped_column(default=0)
    top_score: Mapped[float | None]
    outcome: Mapped[str] = mapped_column(String(16))  # results | no_results | answered | no_answer | error
    cited_chunk_ids: Mapped[list[int] | None] = mapped_column(JSONType)
    supported_ratio: Mapped[float | None]
    latency_ms: Mapped[float | None]
    llm_call_id: Mapped[int | None] = mapped_column(_fk("llm_calls.id", "SET NULL"))
    helpful: Mapped[bool | None]
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AgentRun(Base):
    """One run of the triage agent on a ticket: which planner, what it proposed,
    and what happened to each step (executed, proposed for approval, invalid,
    no change, failed verification) with reasons and timings."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_ticket", "ticket_id"),
        Index("ix_agent_runs_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(_fk("tenants.id"))
    ticket_id: Mapped[int] = mapped_column(_fk("tickets.id", "CASCADE"))
    trigger: Mapped[str] = mapped_column(String(32))  # ticket_created | manual | reindex
    planner: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16))  # completed | failed
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONType)
    latency_ms: Mapped[float | None]
    error: Mapped[str | None] = mapped_column(String(500))
    input_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Feedback(Base):
    """What people tell us: CSAT on a resolved ticket (kind="csat", rating 1–5)
    or free-form product feedback (kind="product"). Real-user evidence for the
    pilot; rows from demo organizations carry their data_origin."""

    __tablename__ = "feedback"
    __table_args__ = (
        Index("ix_feedback_tenant_created", "tenant_id", "created_at"),
        Index("ix_feedback_ticket", "ticket_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(_fk("tenants.id"))
    user_id: Mapped[int | None] = mapped_column(_fk("users.id", "SET NULL"))
    kind: Mapped[str] = mapped_column(String(16))  # csat | product
    ticket_id: Mapped[int | None] = mapped_column(_fk("tickets.id", "CASCADE"))
    rating: Mapped[int | None]
    comment: Mapped[str | None] = mapped_column(Text)
    page: Mapped[str | None] = mapped_column(String(200))
    data_origin: Mapped[str] = mapped_column(String(16), default="real")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AIMonitoringRun(Base):
    """One drift/agreement check for an organization (app/ai/monitoring.py)."""

    __tablename__ = "ai_monitoring"
    __table_args__ = (Index("ix_ai_monitoring_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(_fk("tenants.id"))
    status: Mapped[str] = mapped_column(String(24))  # ok | alert | insufficient_data
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONType)
    alerts: Mapped[list[str]] = mapped_column(JSONType)
    engine_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
