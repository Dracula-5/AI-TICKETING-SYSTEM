"""
Import resolved ticket history from another helpdesk into an organization.

    python -m app.scripts.import_history --org <slug> --csv export.csv [--origin real|synthetic|demo]
        [--create-missing] [--dry-run]

Why: AI recommendations learn from an organization's own resolved tickets, so
a new organization starts cold. Importing its past tickets from the previous
tool gives the AI (and the SLA-risk statistics) history on day one.

CSV columns (header row required):

    title, description, created_at               required
    category, priority, team                     optional labels the AI learns from
    resolved_at                                  optional; rows without it import as open
    requester_email                              optional; unknown addresses become
                                                 inactive requester accounts (no login)

Imported rows are marked with `--origin` (default "real"). Synthetic or demo
history must be marked as such so it is never counted as real usage. Tickets
are embedded by one background `ai.reindex_tenant` job after the import; no
recommendations are issued retroactively for closed work.
"""

import argparse
import csv
import secrets
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.ai.rules import PRIORITIES
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.database import SessionLocal
from app.db.models import Category, Team, Tenant, Ticket, User
from app.services import jobs

ORIGINS = ("real", "synthetic", "demo")


class HistoryImportError(Exception):
    pass


@dataclass
class Report:
    rows: int = 0
    imported: int = 0
    skipped: list[str] = field(default_factory=list)
    created_categories: list[str] = field(default_factory=list)
    created_teams: list[str] = field(default_factory=list)
    created_requesters: int = 0


def _parse_time(value: str) -> datetime:
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def import_rows(
    db: Session,
    tenant: Tenant,
    rows: Iterable[dict[str, str]],
    *,
    origin: str = "real",
    create_missing: bool = False,
    placeholder_domain: str | None = None,
) -> Report:
    if origin not in ORIGINS:
        raise HistoryImportError(f"origin must be one of {ORIGINS}")
    report = Report()
    categories = {c.name.lower(): c.name for c in db.query(Category).filter(Category.tenant_id == tenant.id)}
    teams = {t.name.lower(): t for t in db.query(Team).filter(Team.tenant_id == tenant.id)}
    users = {u.email.lower(): u for u in db.query(User).filter(User.tenant_id == tenant.id)}
    domain = placeholder_domain or f"{tenant.slug}.import.invalid"
    unusable = get_password_hash(secrets.token_urlsafe(32))  # imported requesters cannot log in

    def requester(email: str) -> User:
        email = (email or f"imported-requester@{domain}").strip().lower()
        user = users.get(email)
        if user is None and db.query(User.id).filter(User.email == email).first() is not None:
            # The address belongs to an account in another organization; never
            # attach it here. Keep the history under a placeholder requester.
            return requester(f"imported-requester@{domain}")
        if user is None:
            user = User(
                tenant_id=tenant.id,
                email=email,
                name=email.split("@")[0],
                role="customer",
                hashed_password=unusable,
                is_active=False,
                data_origin=origin,
            )
            db.add(user)
            db.flush()
            users[email] = user
            report.created_requesters += 1
        return user

    for i, row in enumerate(rows, start=2):  # line 1 is the header
        report.rows += 1
        title, description = (row.get("title") or "").strip(), (row.get("description") or "").strip()
        if not title or not description or not row.get("created_at"):
            report.skipped.append(f"line {i}: title, description and created_at are required")
            continue
        try:
            created = _parse_time(row["created_at"])
            resolved = _parse_time(row["resolved_at"]) if (row.get("resolved_at") or "").strip() else None
        except ValueError as e:
            report.skipped.append(f"line {i}: bad timestamp ({e})")
            continue
        if resolved is not None and resolved < created:
            report.skipped.append(f"line {i}: resolved_at is before created_at")
            continue
        priority = (row.get("priority") or "medium").strip().lower()
        if priority not in PRIORITIES:
            report.skipped.append(f"line {i}: unknown priority {priority!r}")
            continue

        category = (row.get("category") or "").strip() or None
        if category is not None and category.lower() not in categories:
            if not create_missing:
                report.skipped.append(f"line {i}: unknown category {category!r} (use --create-missing)")
                continue
            db.add(Category(tenant_id=tenant.id, name=category[:80], keywords=[], is_active=True))
            categories[category.lower()] = category[:80]
            report.created_categories.append(category)
        team_name = (row.get("team") or "").strip() or None
        team = None
        if team_name is not None:
            team = teams.get(team_name.lower())
            if team is None:
                if not create_missing:
                    report.skipped.append(f"line {i}: unknown team {team_name!r} (use --create-missing)")
                    continue
                team = Team(tenant_id=tenant.id, name=team_name[:80])
                db.add(team)
                db.flush()
                teams[team_name.lower()] = team
                report.created_teams.append(team_name)

        tenant.ticket_seq += 1
        db.add(
            Ticket(
                tenant_id=tenant.id,
                number=tenant.ticket_seq,
                title=title[:200],
                description=description,
                priority=priority,
                category=categories[category.lower()] if category else None,
                team_id=team.id if team else None,
                status="closed" if resolved else "submitted",
                channel="import",
                created_by_user_id=requester(row.get("requester_email") or "").id,
                triage_source="manual",
                resolved_at=resolved,
                closed_at=resolved,
                data_origin=origin,
                created_at=created,
                updated_at=resolved or created,
            )
        )
        report.imported += 1
        if report.imported % 500 == 0:
            db.flush()
    if settings.ai_enabled and report.imported:
        jobs.enqueue(db, "ai.reindex_tenant", {"tenant_id": tenant.id}, tenant_id=tenant.id)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("--org", required=True, help="organization slug")
    parser.add_argument("--csv", required=True, help="path to the CSV export")
    parser.add_argument("--origin", default="real", choices=ORIGINS)
    parser.add_argument("--create-missing", action="store_true", help="create unknown categories and teams")
    parser.add_argument("--dry-run", action="store_true", help="validate and report without saving")
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.slug == args.org).first()
        if tenant is None:
            print(f"No organization with slug {args.org!r}", file=sys.stderr)
            return 2
        with open(args.csv, newline="", encoding="utf-8-sig") as f:
            report = import_rows(db, tenant, csv.DictReader(f), origin=args.origin, create_missing=args.create_missing)
        if args.dry_run:
            db.rollback()
        else:
            db.commit()
    finally:
        db.close()
    verb = "Would import" if args.dry_run else "Imported"
    print(f"{verb} {report.imported} of {report.rows} rows into {args.org} (origin={args.origin}).")
    if report.created_categories or report.created_teams:
        print(f"New categories: {len(report.created_categories)}; new teams: {len(report.created_teams)}")
    if report.created_requesters:
        print(f"Inactive requester accounts created: {report.created_requesters}")
    for msg in report.skipped[:20]:
        print(f"  skipped {msg}")
    if len(report.skipped) > 20:
        print(f"  … and {len(report.skipped) - 20} more skipped rows")
    return 0 if not report.skipped else 1


if __name__ == "__main__":
    sys.exit(main())
