import re
import secrets

from sqlalchemy.orm import Session

from app.ai.rules import DEFAULT_CATEGORIES, DEFAULT_TEAMS
from app.db.models import (
    AgentRun,
    AIMonitoringRun,
    AIPrediction,
    Attachment,
    AuditLog,
    Category,
    EmailOutbox,
    Feedback,
    Invitation,
    Job,
    KBChunk,
    KBDocument,
    KBQuery,
    LLMCall,
    Notification,
    RefreshToken,
    SlaPolicy,
    Team,
    TeamMember,
    Tenant,
    Ticket,
    TicketComment,
    TicketEmbedding,
    TicketStatusHistory,
    User,
    UserToken,
)

DEFAULT_ORG_SETTINGS: dict = {
    # Assign newly triaged tickets to the least-loaded agent of the routed team.
    "auto_assign": False,
    # Resolved tickets close automatically if the requester doesn't respond.
    "auto_close_days": 3,
    # Closed tickets can be reopened for this many days.
    "reopen_window_days": 14,
    # Allow people to join this org as requesters from /join/<slug>.
    "portal_signup_enabled": False,
    # When non-empty, portal sign-ups must use one of these email domains.
    "portal_allowed_domains": [],
    # AI (human-in-the-loop policy in app/ai/policy.py). Empty = recommend only.
    "ai_auto_apply_kinds": [],
    "ai_auto_apply_threshold": 0.9,
    # Cosine similarity (all-MiniLM-L6-v2) above which an open/recent ticket is
    # flagged as a possible duplicate. 0.75 = lowest threshold with validation
    # precision >= 0.5 on real duplicates (reports/duplicates/threshold.md:
    # test precision 0.47, recall 0.18). Raise it for fewer, surer flags.
    "ai_duplicate_threshold": 0.75,
    # Minimum number of similar resolved tickets before the AI votes.
    "ai_min_history": 5,
    # Cap on generated-text tokens (input + output) per calendar month.
    "ai_llm_monthly_token_budget": 1_000_000,
}

# (first-response minutes, resolution minutes) per priority. Defaults only —
# each org edits its own policy.
DEFAULT_SLA_MINUTES: dict[str, tuple[int, int]] = {
    "critical": (15, 4 * 60),
    "high": (60, 8 * 60),
    "medium": (4 * 60, 24 * 60),
    "low": (8 * 60, 72 * 60),
}


def org_setting(tenant: Tenant, key: str):
    return (tenant.settings or {}).get(key, DEFAULT_ORG_SETTINGS[key])


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:60] or "org"


def unique_slug(db: Session, name: str) -> str:
    base = slugify(name)
    slug = base
    while db.query(Tenant.id).filter(Tenant.slug == slug).first():
        slug = f"{base}-{secrets.token_hex(2)}"
    return slug


def create_organization(
    db: Session,
    name: str,
    *,
    is_demo: bool = False,
    data_origin: str = "real",
    settings_overrides: dict | None = None,
) -> Tenant:
    """Create an organization provisioned with default teams, categories
    (with routing rules) and SLA policies, so it is usable immediately."""
    tenant = Tenant(
        name=name.strip(),
        slug=unique_slug(db, name),
        is_demo=is_demo,
        data_origin=data_origin,
        settings={**DEFAULT_ORG_SETTINGS, **(settings_overrides or {})},
        ticket_seq=0,
    )
    db.add(tenant)
    db.flush()

    teams = {}
    for team_name, description in DEFAULT_TEAMS:
        team = Team(tenant_id=tenant.id, name=team_name, description=description)
        db.add(team)
        teams[team_name] = team
    db.flush()

    for cat_name, description, keywords, team_name in DEFAULT_CATEGORIES:
        db.add(
            Category(
                tenant_id=tenant.id,
                name=cat_name,
                description=description,
                keywords=list(keywords),
                default_team_id=teams[team_name].id,
            )
        )

    for priority, (first_response, resolution) in DEFAULT_SLA_MINUTES.items():
        db.add(
            SlaPolicy(
                tenant_id=tenant.id,
                priority=priority,
                first_response_minutes=first_response,
                resolution_minutes=resolution,
            )
        )
    db.flush()
    return tenant


def delete_organization(db: Session, tenant: Tenant) -> None:
    """Delete an organization and everything that belongs to it (children before
    parents, so it works without ON DELETE CASCADE). The caller commits. Used to
    re-create demo organizations and by the platform console."""
    tid = tenant.id
    user_ids = [u for (u,) in db.query(User.id).filter(User.tenant_id == tid)]
    for model in (
        Attachment,
        TicketComment,
        TicketStatusHistory,
        Notification,
        AuditLog,
        Invitation,
        EmailOutbox,
        AIPrediction,
        AgentRun,
        AIMonitoringRun,
        Feedback,
        TicketEmbedding,
        Job,
        KBQuery,
        KBChunk,
        KBDocument,
        LLMCall,
    ):
        db.query(model).filter(model.tenant_id == tid).delete(synchronize_session=False)
    db.query(Ticket).filter(Ticket.tenant_id == tid).delete(synchronize_session=False)
    if user_ids:
        for user_model in (TeamMember, RefreshToken, UserToken):
            db.query(user_model).filter(user_model.user_id.in_(user_ids)).delete(synchronize_session=False)
    db.query(Category).filter(Category.tenant_id == tid).delete(synchronize_session=False)
    db.query(SlaPolicy).filter(SlaPolicy.tenant_id == tid).delete(synchronize_session=False)
    db.query(Team).filter(Team.tenant_id == tid).delete(synchronize_session=False)
    db.query(User).filter(User.tenant_id == tid).delete(synchronize_session=False)
    db.delete(tenant)
