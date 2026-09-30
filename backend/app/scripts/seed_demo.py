"""
Seed the three shared demo organizations (DEMO DATA).

    python -m app.scripts.seed_demo            # idempotent: skips orgs that exist
    python -m app.scripts.seed_demo --reset    # delete the demo orgs first, then re-seed

Everything created here is flagged is_demo=True / data_origin="demo", so
dashboards label it and platform metrics can exclude it. Ticket texts are
hand-written illustrative examples, not real user data. Organization names are
invented and every address is under example.com (reserved, undeliverable).

Passwords: DEMO_PASSWORD from the environment if set (use this for a public
"try the demo" login), otherwise a random one printed once at the end.
Demo orgs block password/email changes, invitations and org-setting changes
(see services/guards.py), so shared credentials can't be used to lock others out.
"""

import argparse
import os
import random
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.db.database import SessionLocal, utcnow
from app.db.models import (
    Attachment,
    AuditLog,
    Category,
    EmailOutbox,
    Invitation,
    Notification,
    RefreshToken,
    SlaPolicy,
    Team,
    TeamMember,
    Tenant,
    Ticket,
    TicketComment,
    TicketStatusHistory,
    User,
    UserToken,
)
from app.services import tickets as svc
from app.services.organizations import create_organization

ORGS = [
    {
        "name": "Helix Health (Demo)",
        "domain": "helix-health.example.com",
        "settings": {"auto_assign": True, "portal_signup_enabled": True},
    },
    {"name": "Brightline Retail (Demo)", "domain": "brightline.example.com", "settings": {"auto_assign": False}},
    {"name": "Orbital Engineering (Demo)", "domain": "orbital-eng.example.com", "settings": {"auto_assign": True}},
]

# (role, first name, team memberships)
PEOPLE = [
    ("org_admin", "Avery", []),
    ("manager", "Morgan", ["Service Desk", "Infrastructure"]),
    ("agent", "Jordan", ["Service Desk", "Applications"]),
    ("agent", "Riley", ["Service Desk", "Infrastructure", "Security"]),
    ("agent", "Casey", ["People Operations", "Facilities"]),
    ("analyst", "Quinn", []),
    ("customer", "Taylor", []),
    ("customer", "Sam", []),
    ("customer", "Devon", []),
]

# Illustrative requests (title, description, requester-chosen priority or None).
TICKETS = [
    (
        "VPN disconnects every few minutes",
        "Since the client update my VPN drops every 5-10 minutes when on home wifi.",
        None,
    ),
    (
        "Locked out after password change",
        "I changed my password this morning and now login says my account is locked.",
        None,
    ),
    (
        "Outlook not syncing shared mailbox",
        "The team shared mailbox stopped updating in Outlook yesterday afternoon.",
        None,
    ),
    ("Request: second monitor", "Could I get a second monitor for my desk on floor 4?", "low"),
    (
        "Suspicious email asking for credentials",
        "Got an email that looks like our SSO page asking me to log in. Phishing?",
        None,
    ),
    ("Payslip for last month missing", "My payslip for last month is not in the payroll portal.", None),
    ("Printer on floor 2 jams constantly", "The shared printer near the kitchen jams on every duplex job.", None),
    (
        "Cannot install approved software",
        "Software center fails installing the approved diagram tool with error 1603.",
        None,
    ),
    (
        "Wi-Fi very slow in meeting room B",
        "Video calls keep freezing in meeting room B; wifi speed test shows 2 Mbps.",
        None,
    ),
    ("MFA prompts not arriving", "I'm not receiving MFA push notifications on my phone and can't sign in.", "high"),
    ("Laptop battery drains in an hour", "My laptop battery goes from 100% to 10% in about an hour.", None),
    (
        "Access to finance SharePoint site",
        "I need read access to the finance reporting SharePoint site for the audit.",
        None,
    ),
    (
        "Production reporting server down",
        "The reporting server is down for everyone - dashboards show 502 errors.",
        None,
    ),
    ("Onboarding: new hire starts Monday", "New analyst starts Monday, needs laptop, accounts and a badge.", "medium"),
    ("Air conditioning broken in room 3.12", "Room 3.12 is very hot; AC seems off since this morning.", None),
    ("Excel crashes opening large files", "Excel crashes whenever I open the quarterly model (80 MB).", None),
    (
        "Calendar invites not received",
        "External partners say they sent invites but they never reach my calendar.",
        None,
    ),
    ("Badge not opening parking gate", "My access card works at the door but not at the parking gate.", None),
    ("Leave balance looks wrong", "The HR portal shows 3 days of leave but I should have 8.", None),
    (
        "Possible malware warning on laptop",
        "Antivirus popped up a warning about a quarantined file. Anything to do?",
        None,
    ),
    ("DNS errors for internal wiki", "The internal wiki intermittently fails with DNS_PROBE errors.", None),
    ("Zoom audio echo on laptop", "Everyone hears an echo when I use the laptop's built-in mic in Zoom.", "low"),
    ("Reimbursement claim stuck", "My travel reimbursement has been pending approval for three weeks.", None),
    ("Keyboard keys not responding", "Several keys on my laptop keyboard (E, R, T) stopped working.", None),
]

CUSTOMER_REPLIES = ["Thanks, trying that now.", "Still happening, see details below.", "That worked, thank you!"]
AGENT_REPLIES = [
    "Thanks for reporting - I'm looking into it now.",
    "Could you share a screenshot of the error?",
    "I've applied a fix on our side; please try again.",
]
RESOLUTIONS = [
    "Reset the account and cleared cached credentials.",
    "Updated the client to the latest version and verified the connection.",
    "Replaced the faulty hardware.",
    "Granted access via the standard approval workflow.",
    "Adjusted configuration on the affected service and confirmed with the requester.",
]


def _delete_org(db: Session, tenant: Tenant) -> None:
    tid = tenant.id
    user_ids = [u for (u,) in db.query(User.id).filter(User.tenant_id == tid)]
    for model in (Attachment, TicketComment, TicketStatusHistory, Notification, AuditLog, Invitation, EmailOutbox):
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
    db.commit()


def _backdate_last_history(db: Session, ticket: Ticket, when: datetime) -> None:
    db.flush()  # the session doesn't autoflush; make the newest row visible first
    row = (
        db.query(TicketStatusHistory)
        .filter(TicketStatusHistory.ticket_id == ticket.id)
        .order_by(TicketStatusHistory.id.desc())
        .first()
    )
    if row is not None:
        row.created_at = when


def _backdate_creation_history(db: Session, ticket: Ticket, created: datetime) -> None:
    """create_ticket() may write several rows (submitted, triaged, auto-assigned);
    place them a few seconds apart right after the simulated creation time."""
    db.flush()
    rows = (
        db.query(TicketStatusHistory)
        .filter(TicketStatusHistory.ticket_id == ticket.id)
        .order_by(TicketStatusHistory.id)
        .all()
    )
    for i, row in enumerate(rows):
        row.created_at = created + timedelta(seconds=2 * i)


def _seed_org(db: Session, spec: dict, password_hash: str, rng: random.Random) -> dict:
    tenant = create_organization(
        db, spec["name"], is_demo=True, data_origin="demo", settings_overrides=spec["settings"]
    )
    tenant.domain = spec["domain"]
    teams = {t.name: t for t in db.query(Team).filter(Team.tenant_id == tenant.id)}

    people: dict[str, list[User]] = {}
    for role, first, team_names in PEOPLE:
        user = User(
            name=f"{first} ({role.replace('_', ' ')})",
            email=f"{first.lower()}.{role.replace('_', '')}@{spec['domain']}",
            hashed_password=password_hash,
            role=role,
            tenant_id=tenant.id,
            data_origin="demo",
            email_verified_at=utcnow(),
        )
        db.add(user)
        db.flush()
        for name in team_names:
            db.add(TeamMember(team_id=teams[name].id, user_id=user.id))
        people.setdefault(role, []).append(user)
    db.flush()

    agents = people["agent"] + people["manager"]
    customers = people["customer"]
    now = utcnow()
    for title, description, priority in rng.sample(TICKETS, k=18):
        created = now - timedelta(days=rng.uniform(0.1, 13.5), minutes=rng.randint(0, 600))
        ticket = svc.create_ticket(
            db,
            requester=rng.choice(customers),
            title=title,
            description=description,
            priority=priority,
            data_origin="demo",
            created_at=created,
        )
        _backdate_creation_history(db, ticket, created)
        _play_lifecycle(db, ticket, created, agents, rng)
    db.commit()
    return {"org": tenant.name, "slug": tenant.slug, "users": {r: [u.email for u in us] for r, us in people.items()}}


def _play_lifecycle(db: Session, ticket: Ticket, created: datetime, agents: list[User], rng: random.Random) -> None:
    """Advance a ticket through a plausible share of its lifecycle, with
    timestamps spread after its creation time."""
    S = svc.TicketStatus
    stage = rng.choices(
        ["new", "assigned", "in_progress", "waiting", "escalated", "resolved", "closed"],
        weights=[2, 2, 3, 2, 1, 2, 5],
    )[0]
    if stage == "new":
        return

    clock = created
    requester = ticket.requester

    def step(minutes_low: int, minutes_high: int) -> datetime:
        nonlocal clock
        clock = min(clock + timedelta(minutes=rng.randint(minutes_low, minutes_high)), utcnow())
        return clock

    agent = ticket.assignee or rng.choice(agents)
    if ticket.assigned_to_user_id is None:
        svc.assign(db, ticket, assignee_id=agent.id, actor=agents[-1], reason="Assigned from the team queue")
    _backdate_last_history(db, ticket, step(5, 90))
    if stage == "assigned":
        return

    svc.transition(db, ticket, S.ACKNOWLEDGED, actor=agent)
    ticket.acknowledged_at = ticket.first_responded_at = step(2, 60)
    _backdate_last_history(db, ticket, clock)
    db.add(
        TicketComment(
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            author_user_id=agent.id,
            visibility="public",
            content=AGENT_REPLIES[0],
            created_at=clock,
        )
    )
    svc.transition(db, ticket, S.IN_PROGRESS, actor=agent)
    _backdate_last_history(db, ticket, step(5, 120))
    if stage == "in_progress":
        return
    if stage == "waiting":
        svc.transition(db, ticket, S.WAITING_FOR_CUSTOMER, actor=agent, reason=AGENT_REPLIES[1])
        ticket.sla_paused_at = step(5, 60)
        _backdate_last_history(db, ticket, clock)
        return
    if stage == "escalated":
        svc.transition(db, ticket, S.ESCALATED, actor=agent, reason="Needs second-line support")
        _backdate_last_history(db, ticket, step(30, 240))
        return

    db.add(
        TicketComment(
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            author_user_id=requester.id,
            visibility="public",
            content=rng.choice(CUSTOMER_REPLIES),
            created_at=step(10, 240),
        )
    )
    svc.transition(db, ticket, S.RESOLVED, actor=agent, resolution_summary=rng.choice(RESOLUTIONS))
    ticket.resolved_at = step(30, 60 * 20)
    _backdate_last_history(db, ticket, clock)
    if stage == "closed":
        svc.transition(db, ticket, S.CLOSED, actor=requester, reason="Requester confirmed the resolution")
        ticket.closed_at = step(10, 60 * 12)
        _backdate_last_history(db, ticket, clock)


def seed(reset: bool = False, seed_value: int = 7) -> dict:
    rng = random.Random(seed_value)
    password = os.environ.get("DEMO_PASSWORD") or secrets.token_urlsafe(12)
    password_hash = get_password_hash(password)
    db = SessionLocal()
    created = []
    try:
        for spec in ORGS:
            existing = db.query(Tenant).filter(Tenant.name == spec["name"], Tenant.is_demo.is_(True)).first()
            if existing and reset:
                _delete_org(db, existing)
                existing = None
            if existing:
                continue
            created.append(_seed_org(db, spec, password_hash, rng))
    finally:
        db.close()
    return {"password": password if created else None, "created": created}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--reset", action="store_true", help="delete and re-create the demo organizations")
    args = parser.parse_args()
    result = seed(reset=args.reset)
    if not result["created"]:
        print("Demo organizations already exist; nothing to do (use --reset to re-create).")
        return
    for org in result["created"]:
        print(f"\n{org['org']}  (portal slug: {org['slug']})")
        for role, emails in org["users"].items():
            print(f"  {role:10} {', '.join(emails)}")
    if not os.environ.get("DEMO_PASSWORD"):
        print(f"\nGenerated password for all demo accounts (shown once): {result['password']}")


if __name__ == "__main__":
    main()
