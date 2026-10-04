"""
Seed the three shared demo organizations (DEMO DATA).

    python -m app.scripts.seed_demo            # idempotent: skips up-to-date demo orgs
    python -m app.scripts.seed_demo --reset    # delete the demo orgs first, then re-seed

Each organization gets people in every role, about 70 tickets spread over the
last six weeks at every stage of the workflow (replies, resolutions, requester
ratings), help articles and product feedback — enough for queues, SLA views,
dashboards, the knowledge base and AI recommendations to show something.

Everything created here is flagged is_demo=True / data_origin="demo", so
dashboards label it and platform metrics can exclude it. Ticket texts are
hand-written illustrative examples, not real user data. Organization names are
invented and every address is under example.com (reserved, undeliverable).

Demo organizations seeded by an older SEED_VERSION are re-created (their
content is disposable by definition); organizations that are not demo are never
touched.

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

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.database import SessionLocal, utcnow
from app.db.models import (
    Feedback,
    Team,
    TeamMember,
    Tenant,
    Ticket,
    TicketComment,
    TicketStatusHistory,
    User,
)
from app.kb import ingest
from app.services import jobs
from app.services import tickets as svc
from app.services.organizations import create_organization, delete_organization

# Bump when the seeded content changes: demo organizations with an older version are re-created.
SEED_VERSION = 2
TICKETS_PER_ORG = 70
HISTORY_DAYS = 45

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
    ("agent", "Parker", ["Applications", "Security"]),
    ("analyst", "Quinn", []),
    ("customer", "Taylor", []),
    ("customer", "Sam", []),
    ("customer", "Devon", []),
    ("customer", "Alex", []),
    ("customer", "Jamie", []),
    ("customer", "Robin", []),
]

# Illustrative requests: (title, description, requester-chosen priority or None, variants).
# "{v}" is replaced by one of the variants, so the same kind of problem recurs with
# different details — the way a real service desk sees it.
TICKETS: list[tuple[str, str, str | None, list[str]]] = [
    (
        "VPN disconnects every few minutes {v}",
        "Since the client update my VPN drops every 5-10 minutes {v}. Reconnecting works for a while.",
        None,
        ["on home wifi", "on the office guest network", "when tethering from my phone"],
    ),
    (
        "Locked out after password change",
        "I changed my password {v} and now login says my account is locked.",
        None,
        ["this morning", "after the expiry reminder", "from the self-service page"],
    ),
    (
        "Outlook not syncing {v}",
        "{v} stopped updating in Outlook yesterday afternoon; webmail shows the new messages.",
        None,
        ["the shared mailbox", "my inbox", "the team calendar"],
    ),
    (
        "Request: {v}",
        "Could I get {v} for my desk? My manager has approved it.",
        "low",
        ["a second monitor", "a docking station", "a wireless headset"],
    ),
    (
        "Suspicious email asking for credentials",
        "Got an email that looks like {v} asking me to log in. Phishing? I have not clicked anything.",
        None,
        ["our SSO page", "a payroll notice", "a parcel delivery notice"],
    ),
    (
        "Payslip for {v} missing",
        "My payslip for {v} is not in the payroll portal, the earlier ones are there.",
        None,
        ["last month", "the bonus run", "my first month"],
    ),
    (
        "Printer on {v} jams constantly",
        "The shared printer on {v} jams on every duplex job and shows a paper-path error.",
        None,
        ["floor 2", "floor 5", "the reception desk"],
    ),
    (
        "Cannot install approved software",
        "Software center fails installing {v} with error 1603. It is on the approved list.",
        None,
        ["the diagram tool", "the PDF editor", "the statistics package"],
    ),
    (
        "Wi-Fi very slow in {v}",
        "Video calls keep freezing in {v}; a wifi speed test shows about 2 Mbps.",
        None,
        ["meeting room B", "the east wing", "the cafeteria"],
    ),
    (
        "MFA prompts not arriving",
        "I'm not receiving MFA push notifications {v} and can't sign in to anything.",
        "high",
        ["on my phone", "since I changed phones", "while travelling abroad"],
    ),
    (
        "Laptop battery drains in an hour",
        "My laptop battery goes from 100% to 10% in about an hour {v}.",
        None,
        ["even when idle", "since the last update", "when on video calls"],
    ),
    (
        "Access to {v}",
        "I need read access to {v} for the audit that starts next week.",
        None,
        ["the finance SharePoint site", "the project archive share", "the vendor contracts folder"],
    ),
    (
        "Production {v} down",
        "The {v} is down for everyone - pages show 502 errors since a few minutes ago.",
        None,
        ["reporting server", "intranet", "document management system"],
    ),
    (
        "Onboarding: new hire starts {v}",
        "A new colleague starts {v} and needs a laptop, accounts and a badge.",
        "medium",
        ["Monday", "on the 1st", "next week"],
    ),
    (
        "Air conditioning broken in {v}",
        "{v} is very hot; the air conditioning seems to be off since this morning.",
        None,
        ["room 3.12", "the open office on floor 4", "the server room anteroom"],
    ),
    (
        "Excel crashes opening large files",
        "Excel crashes whenever I open {v}. Smaller workbooks are fine.",
        None,
        ["the quarterly model (80 MB)", "the pricing workbook", "files with Power Query"],
    ),
    (
        "Calendar invites not received",
        "{v} say they sent invites but they never reach my calendar.",
        None,
        ["External partners", "Colleagues in another office", "Our customers"],
    ),
    (
        "Badge not opening {v}",
        "My access card works at the front door but not at {v}.",
        None,
        ["the parking gate", "the bike storage", "the lab on floor 1"],
    ),
    (
        "Leave balance looks wrong",
        "The HR portal shows {v} of leave but that does not match my own count.",
        None,
        ["3 days", "a negative balance", "last year's carry-over missing"],
    ),
    (
        "Possible malware warning on laptop",
        "Antivirus popped up a warning about {v}. Is there anything I should do?",
        None,
        ["a quarantined file", "a blocked download", "a suspicious browser extension"],
    ),
    (
        "DNS errors for {v}",
        "{v} intermittently fails with DNS_PROBE errors; a reload usually helps.",
        None,
        ["the internal wiki", "the time-tracking site", "the build server"],
    ),
    (
        "Zoom audio echo on laptop",
        "Everyone hears an echo when I use {v} in Zoom.",
        "low",
        ["the laptop's built-in mic", "the meeting room speaker", "my USB headset"],
    ),
    (
        "Reimbursement claim stuck",
        "My {v} reimbursement has been pending approval for three weeks.",
        None,
        ["travel", "training", "home-office equipment"],
    ),
    (
        "Keyboard keys not responding",
        "Several keys on my {v} stopped working (E, R, T).",
        None,
        ["laptop keyboard", "external keyboard", "docked keyboard"],
    ),
    (
        "Shared drive is read-only",
        "I can open files on {v} but saving fails with 'access denied'.",
        None,
        ["the marketing share", "the team drive", "the scans folder"],
    ),
    (
        "Teams calls drop after a minute",
        "Teams calls {v} drop after about a minute; chat keeps working.",
        None,
        ["from the office network", "with external guests", "on the meeting room device"],
    ),
    (
        "License expired for {v}",
        "{v} says my license has expired and opens in read-only mode.",
        None,
        ["the design suite", "the CAD viewer", "the project planning tool"],
    ),
    (
        "New laptop is missing software",
        "My replacement laptop arrived without {v}; I need it for daily work.",
        None,
        ["the VPN client", "the accounting application", "the office suite"],
    ),
    (
        "Offboarding: colleague leaves {v}",
        "A team member leaves {v}. Please disable accounts and collect the equipment.",
        "medium",
        ["on Friday", "at the end of the month", "today"],
    ),
    (
        "Monitor flickers when docked",
        "My external monitor flickers {v} when the laptop is on the docking station.",
        None,
        ["every few seconds", "after waking from sleep", "at full resolution"],
    ),
    (
        "Cannot join the {v} network",
        "My device no longer connects to the {v} network; it asks for credentials and then fails.",
        None,
        ["staff wifi", "wired office", "warehouse wifi"],
    ),
    (
        "Spam flood in my inbox",
        "I have been getting dozens of spam messages {v} since yesterday.",
        None,
        ["about invoices", "in another language", "from lookalike addresses"],
    ),
    (
        "Meeting room display not working",
        "The display in {v} stays black when a laptop is connected by HDMI or wireless.",
        None,
        ["meeting room A", "the board room", "the training room"],
    ),
    (
        "Update restarts my laptop during work",
        "A forced update restarted my laptop {v} and I lost unsaved work. Can it be scheduled?",
        "low",
        ["in the middle of a call", "twice this week", "during a presentation"],
    ),
    (
        "Benefits enrolment question",
        "I cannot find where to change {v} in the HR portal before the deadline.",
        None,
        ["my pension contribution", "my health plan", "my commuter benefit"],
    ),
    (
        "Desk lights flicker in {v}",
        "The ceiling lights in {v} flicker all day; it is hard to work there.",
        "low",
        ["the open office", "the corridor on floor 2", "meeting room C"],
    ),
    (
        "Account shows sign-ins I did not make",
        "The sign-in history of my account shows {v} that was not me.",
        "high",
        ["a login from another country", "several failed attempts at night", "a new device I do not own"],
    ),
    (
        "OneDrive stuck syncing",
        "OneDrive has shown 'processing changes' for {v} and files are not uploading.",
        None,
        ["two days", "a folder with many small files", "one large video"],
    ),
    (
        "Mouse pointer lags",
        "The pointer of my {v} lags and jumps; a restart helps only briefly.",
        "low",
        ["wireless mouse", "laptop touchpad", "Bluetooth mouse"],
    ),
    (
        "Firewall blocks {v}",
        "{v} is blocked by the firewall with a 'category not allowed' page. We need it for work.",
        None,
        ["a supplier portal", "a government tax site", "a customer's file transfer site"],
    ),
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
CSAT_COMMENTS = [
    None,
    None,
    "Quick and clear, thanks.",
    "Solved, but it took a few reminders.",
    "Great help.",
    "Fixed on the first try.",
    "Took longer than I hoped.",
]
PRODUCT_FEEDBACK = [
    ("/tickets", "Would be nice to filter my tickets by category."),
    ("/kb", "The help articles answered my VPN question before I opened a ticket."),
]

# Help articles: (title, visibility, Markdown body).
ARTICLES = [
    (
        "Fix VPN disconnects",
        "public",
        "# Fix VPN disconnects\n\n"
        "## Check the basics\n\nMake sure the VPN client is on the current version (Help > About). Older "
        "versions drop the tunnel every few minutes on some home routers.\n\n"
        "## Home wifi\n\nSwitch the router to the 5 GHz band or use a cable. If the VPN drops only on wifi, "
        "disable 'wifi power saving' in the adapter settings.\n\n"
        "## Still disconnecting\n\nOpen a ticket and include the time of the last disconnect and whether you "
        "were on wifi, cable or a phone hotspot.\n",
    ),
    (
        "Reset your password or unlock your account",
        "public",
        "# Reset your password or unlock your account\n\n"
        "## Self-service reset\n\nUse 'Forgot password' on the sign-in page. The link is valid for 30 minutes.\n\n"
        "## Locked out\n\nFive wrong attempts lock the account for 15 minutes. After a password change, update "
        "the password on your phone's mail app too - old saved passwords keep locking the account.\n\n"
        "## MFA not arriving\n\nCheck that notifications are allowed for the authenticator app and that the "
        "phone has a data connection. A new phone must be registered again by the service desk.\n",
    ),
    (
        "Report a suspicious email",
        "public",
        "# Report a suspicious email\n\n"
        "## Do not click\n\nDo not open links or attachments. Do not reply.\n\n"
        "## Report it\n\nUse the 'Report phishing' button in the mail client, or forward the message as an "
        "attachment to the security team through a ticket in the Security category.\n\n"
        "## If you already clicked\n\nChange your password immediately and open a high-priority ticket so "
        "the security team can check the sign-in history of your account.\n",
    ),
    (
        "Printer jams and paper-path errors",
        "public",
        "# Printer jams and paper-path errors\n\n"
        "## Clear the jam\n\nOpen the rear door and tray 2, remove all paper including torn pieces, and close "
        "both until they click.\n\n"
        "## Duplex jobs\n\nJams on every duplex job usually mean the duplex unit is not seated. Pull it out "
        "and push it back in.\n\n"
        "## Keeps happening\n\nOpen a ticket with the printer's location and the error code on its display.\n",
    ),
    (
        "New hire checklist for managers",
        "public",
        "# New hire checklist for managers\n\n"
        "## One week before\n\nOpen an onboarding ticket with the start date, role and required software. "
        "Laptops need three working days.\n\n"
        "## First day\n\nThe badge is collected at reception. Accounts are active from 08:00 on the start "
        "date; the first sign-in asks to set a password and register MFA.\n",
    ),
    (
        "Runbook: reporting server returns 502",
        "internal",
        "# Runbook: reporting server returns 502\n\n"
        "## Triage\n\nCheck the application pool and the database connection first. A 502 for everyone "
        "usually means the app service stopped after patching.\n\n"
        "## Fix\n\nRestart the reporting service, then verify the health page. If the database is "
        "unreachable, escalate to Infrastructure as a critical incident.\n\n"
        "## Afterwards\n\nPost a status note on the affected tickets and link them as duplicates of the "
        "first report.\n",
    ),
]


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


def _ticket_texts(rng: random.Random, count: int) -> list[tuple[str, str, str | None]]:
    pool = [
        (title.replace("{v}", v), description.replace("{v}", v), priority)
        for title, description, priority, variants in TICKETS
        for v in variants
    ]
    rng.shuffle(pool)
    # Distinct titles first; the same title with other details only fills what is left.
    unique: list[tuple[str, str, str | None]] = []
    rest: list[tuple[str, str, str | None]] = []
    seen: set[str] = set()
    for text in pool:
        (rest if text[0] in seen else unique).append(text)
        seen.add(text[0])
    return (unique + rest)[:count]


def _seed_org(db: Session, spec: dict, password_hash: str, rng: random.Random) -> dict:
    tenant = create_organization(
        db,
        spec["name"],
        is_demo=True,
        data_origin="demo",
        settings_overrides={**spec["settings"], "demo_seed_version": SEED_VERSION},
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
    for title, description, priority in _ticket_texts(rng, TICKETS_PER_ORG):
        stage = rng.choices(STAGES, weights=STAGE_WEIGHTS)[0]
        created = now - timedelta(days=_age_days(stage, rng))
        ticket = svc.create_ticket(
            db,
            requester=rng.choice(customers),
            title=title,
            description=description,
            priority=priority,
            data_origin="demo",
            created_at=created,
            analyze=False,  # history is indexed once below, not triaged after the fact
        )
        _backdate_creation_history(db, ticket, created)
        _play_lifecycle(db, ticket, created, agents, rng, stage)

    admin = people["org_admin"][0]
    for title, visibility, body in ARTICLES:
        slug = title.lower().replace(" ", "-").replace(":", "")
        ingest.create_document(
            db,
            user=admin,
            filename=f"{slug}.md",
            data=body.encode(),
            visibility=visibility,
            title=title,
            data_origin="demo",
        )
    for (page, comment), user in zip(PRODUCT_FEEDBACK, customers, strict=False):
        db.add(
            Feedback(
                tenant_id=tenant.id,
                user_id=user.id,
                kind="product",
                comment=comment,
                page=page,
                data_origin="demo",
                created_at=now - timedelta(days=rng.uniform(1, 20)),
            )
        )

    if settings.ai_enabled:
        jobs.enqueue(db, "ai.reindex_tenant", {"tenant_id": tenant.id, "triage_open": True}, tenant_id=tenant.id)
    db.commit()
    return {"org": tenant.name, "slug": tenant.slug, "users": {r: [u.email for u in us] for r, us in people.items()}}


STAGES = ["new", "assigned", "in_progress", "waiting", "escalated", "resolved", "closed"]
STAGE_WEIGHTS = [4, 5, 7, 4, 2, 6, 42]  # mostly finished history, a working backlog on top


def _age_days(stage: str, rng: random.Random) -> float:
    """How long ago a ticket at this stage was created. Finished tickets fill the
    whole history; open ones are mostly recent enough to be inside their SLA
    (the SLA sweep escalates what is overdue), with some overdue work left in."""
    if stage == "closed":
        return rng.uniform(0.3, HISTORY_DAYS)
    if stage == "resolved":
        return rng.uniform(0.2, 2.5)  # older resolved tickets auto-close
    if stage == "new":
        return rng.uniform(0.005, 0.15)
    if stage == "assigned":
        return rng.uniform(0.01, 0.2)
    if stage == "in_progress":
        return rng.uniform(0.05, 1.2) if rng.random() < 0.75 else rng.uniform(2, 9)
    if stage == "waiting":
        return rng.uniform(0.1, 6)
    return rng.uniform(0.2, 5)  # escalated


def _play_lifecycle(
    db: Session, ticket: Ticket, created: datetime, agents: list[User], rng: random.Random, stage: str
) -> None:
    """Advance a ticket to the given stage, with timestamps spread after its creation time."""
    S = svc.TicketStatus
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
    if rng.random() < 0.6:  # most requesters rate a finished ticket
        db.add(
            Feedback(
                tenant_id=ticket.tenant_id,
                user_id=requester.id,
                kind="csat",
                ticket_id=ticket.id,
                rating=rng.choices([1, 2, 3, 4, 5], weights=[1, 1, 3, 8, 10])[0],
                comment=rng.choice(CSAT_COMMENTS),
                data_origin="demo",
                created_at=clock,
            )
        )


def _outdated(tenant: Tenant) -> bool:
    return int((tenant.settings or {}).get("demo_seed_version", 1)) < SEED_VERSION


def seed(reset: bool = False, seed_value: int = 7) -> dict:
    rng = random.Random(seed_value)
    password = os.environ.get("DEMO_PASSWORD") or secrets.token_urlsafe(12)
    password_hash = None  # hashed only when an organization is created (bcrypt is slow on small hosts)
    db = SessionLocal()
    created = []
    try:
        for spec in ORGS:
            existing = db.query(Tenant).filter(Tenant.name == spec["name"], Tenant.is_demo.is_(True)).first()
            if existing and (reset or _outdated(existing)):
                delete_organization(db, existing)
                db.commit()
                existing = None
            if existing:
                continue
            password_hash = password_hash or get_password_hash(password)
            created.append(_seed_org(db, spec, password_hash, rng))
    finally:
        db.close()
    return {"password": password if created else None, "created": created}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--reset", action="store_true", help="delete and re-create the demo organizations")
    args = parser.parse_args()
    run(reset=args.reset)


def run(reset: bool = False) -> None:
    result = seed(reset=reset)
    if not result["created"]:
        print("Demo organizations are up to date; nothing to do (use --reset to re-create).")
        return
    for org in result["created"]:
        print(f"\n{org['org']}  (portal slug: {org['slug']})")
        for role, emails in org["users"].items():
            print(f"  {role:10} {', '.join(emails)}")
    if not os.environ.get("DEMO_PASSWORD"):
        print(f"\nGenerated password for all demo accounts (shown once): {result['password']}")


if __name__ == "__main__":
    main()
