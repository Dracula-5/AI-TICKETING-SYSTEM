"""
Volume data for load and database-scalability tests (P10/P11). SYNTHETIC.

    python -m app.scripts.seed_volume --tickets 100000 [--reset] [--tokens-out tokens.json]

Creates (or extends) one organization, "Load Test (Synthetic)" — flagged as a
demo organization with data_origin=synthetic so none of it can be mistaken for
real usage — with agents, managers and requesters, then bulk-inserts tickets
spread over the past year with a realistic mix of status, priority, category,
assignment and SLA fields, one status-history row per ticket and a public
comment on some. `--tokens-out` writes access tokens for the load generator
(minted directly: load tests measure the API, not bcrypt against the login
rate limit). Tokens live for ACCESS_TOKEN_EXPIRE_MINUTES.

Never run this against a production database.
"""

import argparse
import json
import random
import secrets
import sys
import time
from datetime import timedelta

from sqlalchemy import insert, select, text

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.db.database import SessionLocal, utcnow
from app.db.models import Category, SlaPolicy, TeamMember, Tenant, Ticket, TicketComment, TicketStatusHistory, User
from app.services.organizations import create_organization

ORG_NAME = "Load Test (Synthetic)"
BATCH = 5000

TEMPLATES = {
    "Network & Connectivity": [
        ("VPN disconnects every few minutes", "The VPN client drops the tunnel on home wifi; error 809 sometimes."),
        ("Wi-Fi unreachable on floor {n}", "Laptops on floor {n} cannot join the corporate wifi since this morning."),
        ("Slow network to the file server", "Copying files to the shared drive takes minutes instead of seconds."),
    ],
    "Hardware": [
        ("Printer jams on floor {n}", "The printer on floor {n} jams on every duplex job."),
        ("Laptop battery drains fast", "My laptop battery lasts under an hour after the last update."),
        ("Second monitor not detected", "The docking station no longer detects my second monitor."),
    ],
    "Access & Identity": [
        ("Password reset needed", "I am locked out of my account after too many attempts."),
        ("Access to the finance share", "I need read access to the finance shared folder for the audit."),
        ("MFA prompt keeps failing", "The authenticator app codes are rejected when I sign in."),
    ],
    "Software & Applications": [
        ("Outlook crashes on start", "Outlook closes immediately after opening since yesterday's update."),
        ("Install request: {n}", "Please install version {n} of the statistics package on my machine."),
        ("Excel macro error", "The monthly report macro fails with a runtime error 1004."),
    ],
    "Security": [
        ("Suspicious email received", "I received an email asking me to confirm my password on an unknown site."),
        ("Lost company phone", "I lost my company phone on the train this morning; please lock it."),
    ],
}
PRIORITIES = [("critical", 0.05), ("high", 0.25), ("medium", 0.5), ("low", 0.2)]
STATUSES = [
    ("closed", 0.55),
    ("resolved", 0.15),
    ("in_progress", 0.08),
    ("assigned", 0.07),
    ("acknowledged", 0.03),
    ("waiting_for_customer", 0.04),
    ("triaged", 0.05),
    ("submitted", 0.03),
]


def _pick(rng: random.Random, weighted):
    r, acc = rng.random(), 0.0
    for value, w in weighted:
        acc += w
        if r < acc:
            return value
    return weighted[-1][0]


def _org(db, reset: bool) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.name == ORG_NAME).first()
    if tenant is not None and reset:
        tid = tenant.id
        for table in (
            "ai_predictions",
            "agent_runs",
            "ticket_embeddings",
            "feedback",
            "attachments",
            "ticket_comments",
            "ticket_status_history",
            "notifications",
            "audit_logs",
            "email_outbox",
            "jobs",
            "kb_queries",
            "kb_chunks",
            "kb_documents",
            "llm_calls",
            "tickets",
        ):
            db.execute(text(f"DELETE FROM {table} WHERE tenant_id = :t"), {"t": tid})  # noqa: S608  # nosec B608 -- fixed table names, no input
        db.commit()
        tenant.ticket_seq = 0
    if tenant is None:
        tenant = create_organization(db, ORG_NAME, is_demo=True, data_origin="synthetic")
        db.flush()
    return tenant


def _users(db, tenant: Tenant, rng: random.Random) -> dict[str, list[User]]:
    existing = db.query(User).filter(User.tenant_id == tenant.id).all()
    if existing:
        out: dict[str, list[User]] = {}
        for u in existing:
            out.setdefault(u.role, []).append(u)
        return out
    unusable = get_password_hash(secrets.token_urlsafe(24))
    teams = [t for t in tenant_teams(db, tenant)]
    out = {"org_admin": [], "manager": [], "agent": [], "customer": []}
    plan = [("org_admin", 1), ("manager", 2), ("agent", 20), ("customer", 300)]
    for role, n in plan:
        for i in range(n):
            u = User(
                tenant_id=tenant.id,
                role=role,
                name=f"{role.title()} {i}",
                hashed_password=unusable,
                email=f"{role}.{i}.{tenant.slug}@loadtest.invalid",
                data_origin="synthetic",
                email_verified_at=utcnow(),
            )
            db.add(u)
            out[role].append(u)
    db.flush()
    for i, agent in enumerate(out["agent"] + out["manager"]):
        db.add(TeamMember(team_id=teams[i % len(teams)].id, user_id=agent.id))
    db.flush()
    return out


def tenant_teams(db, tenant):
    from app.db.models import Team

    return db.query(Team).filter(Team.tenant_id == tenant.id).order_by(Team.id).all()


def seed(n_tickets: int, reset: bool = False, seed_value: int = 3) -> dict:
    rng = random.Random(seed_value)
    db = SessionLocal()
    started = time.perf_counter()
    try:
        tenant = _org(db, reset)
        people = _users(db, tenant, rng)
        cats = {c.name: c for c in db.query(Category).filter(Category.tenant_id == tenant.id)}
        templates = [(name, t) for name, ts in TEMPLATES.items() if name in cats for t in ts]
        policy = {p.priority: p for p in db.query(SlaPolicy).filter(SlaPolicy.tenant_id == tenant.id)}
        agents = people["agent"] + people["manager"]
        customers = people["customer"]
        now = utcnow()
        start_number = tenant.ticket_seq
        db.commit()

        done = 0
        while done < n_tickets:
            rows, hist, comments = [], [], []
            for i in range(min(BATCH, n_tickets - done)):
                number = start_number + done + i + 1
                cat, (title, desc) = rng.choice(templates)
                k = rng.randint(1, 9)
                created = now - timedelta(minutes=rng.randint(5, 365 * 24 * 60))
                pri = _pick(rng, PRIORITIES)
                status = (
                    _pick(rng, STATUSES)
                    if created < now - timedelta(days=2)
                    else rng.choice(["submitted", "triaged", "assigned", "in_progress"])
                )
                pol = policy[pri]
                assigned = status not in ("submitted", "triaged")
                resolved_at = (
                    created + timedelta(minutes=rng.lognormvariate(6.5, 1.3))
                    if status in ("resolved", "closed")
                    else None
                )
                if resolved_at and resolved_at > now:
                    resolved_at = now
                res_due = created + timedelta(minutes=pol.resolution_minutes)
                rows.append(
                    {
                        "tenant_id": tenant.id,
                        "number": number,
                        "title": title.format(n=k),
                        "description": desc.format(n=k),
                        "priority": pri,
                        "category": cat,
                        "status": status,
                        "channel": "web",
                        "created_by_user_id": rng.choice(customers).id,
                        "assigned_to_user_id": rng.choice(agents).id if assigned else None,
                        "team_id": cats[cat].default_team_id,
                        "triage_source": "rules",
                        "first_response_due": created + timedelta(minutes=pol.first_response_minutes),
                        "first_responded_at": created + timedelta(minutes=rng.randint(2, 300)) if assigned else None,
                        "resolution_due": res_due,
                        "resolution_breached_at": res_due if (resolved_at or now) > res_due else None,
                        "resolved_at": resolved_at,
                        "closed_at": resolved_at if status == "closed" else None,
                        "reopened_count": 0,
                        "data_origin": "synthetic",
                        "created_at": created,
                        "updated_at": resolved_at or created,
                    }
                )
            db.execute(insert(Ticket), rows)
            ids = db.execute(
                select(Ticket.id, Ticket.created_at, Ticket.created_by_user_id, Ticket.number).where(
                    Ticket.tenant_id == tenant.id,
                    Ticket.number > start_number + done,
                    Ticket.number <= start_number + done + len(rows),
                )
            ).all()
            for tid, created, requester, _ in ids:
                hist.append(
                    {
                        "tenant_id": tenant.id,
                        "ticket_id": tid,
                        "from_status": None,
                        "to_status": "submitted",
                        "actor_user_id": requester,
                        "actor_type": "user",
                        "created_at": created,
                    }
                )
                if rng.random() < 0.3:
                    comments.append(
                        {
                            "tenant_id": tenant.id,
                            "ticket_id": tid,
                            "author_user_id": requester,
                            "visibility": "public",
                            "content": "Any update on this?",
                            "created_at": created + timedelta(hours=2),
                        }
                    )
            db.execute(insert(TicketStatusHistory), hist)
            if comments:
                db.execute(insert(TicketComment), comments)
            done += len(rows)
            tenant.ticket_seq = start_number + done
            db.commit()
            print(f"  {done:,}/{n_tickets:,} tickets", file=sys.stderr, flush=True)
        db.execute(text("ANALYZE tickets")) if db.get_bind().dialect.name == "postgresql" else None
        db.commit()
        total = db.query(Ticket).filter(Ticket.tenant_id == tenant.id).count()
        return {
            "organization": tenant.name,
            "slug": tenant.slug,
            "tenant_id": tenant.id,
            "tickets_total": total,
            "inserted": n_tickets,
            "seconds": round(time.perf_counter() - started, 1),
            "users": {r: len(u) for r, u in people.items()},
        }
    finally:
        db.close()


def tokens(tenant_slug: str) -> dict:
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).one()
        out: dict[str, list] = {}
        for u in db.query(User).filter(User.tenant_id == tenant.id, User.is_active.is_(True)):
            token, _ = create_access_token(u.id, u.tenant_id, u.role)
            out.setdefault(u.role, []).append({"id": u.id, "token": token})
        return {"expires_minutes": settings.access_token_expire_minutes, "tenant_id": tenant.id, "users": out}
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tickets", type=int, default=10_000)
    parser.add_argument("--reset", action="store_true", help="delete the load-test organization's tickets first")
    parser.add_argument("--tokens-out", help="write access tokens for the load generator to this file")
    args = parser.parse_args(argv)
    if settings.environment == "production":
        print("Refusing to seed volume data in ENVIRONMENT=production", file=sys.stderr)
        return 2
    result = seed(args.tickets, reset=args.reset) if args.tickets > 0 else None
    if result:
        print(json.dumps(result, indent=2))
    if args.tokens_out:
        slug = result["slug"] if result else None
        if slug is None:
            db = SessionLocal()
            slug = db.query(Tenant.slug).filter(Tenant.name == ORG_NAME).scalar()
            db.close()
        with open(args.tokens_out, "w", encoding="utf-8") as f:
            json.dump(tokens(slug), f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
