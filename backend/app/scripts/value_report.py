"""
Value report for one organization (P16): measured counts × the owner's own
assumptions, with every input printed next to the result.

    python -m app.scripts.value_report --org <slug> --days 30 \\
        --triage-minutes 3 --reply-minutes 5 --hourly-cost 40 [--currency EUR]

What is measured (from the database, this organization only):
  * recommendations people accepted or edited (triage/routing work the AI prepared),
  * changes applied automatically and not reverted,
  * reply drafts sent (accepted or edited),
  * knowledge-base answers rated helpful by requesters.

What is assumed (you supply it; nothing is defaulted): minutes of manual work
each of those replaces, and the loaded hourly cost of that work. The output is
an *estimate of time handled with AI assistance* — not a measured saving. A
measured saving needs a before/after comparison (docs/pilot_plan.md §5).
Demo and synthetic organizations are labelled as such.
"""

import argparse
import sys
from datetime import timedelta

from sqlalchemy import func

from app.db.database import SessionLocal, utcnow
from app.db.models import AIPrediction, KBQuery, Tenant

TRIAGE_KINDS = ("category", "priority", "team", "assignee", "duplicate", "request_info", "escalate")


def compute(db, tenant: Tenant, days: int) -> dict:
    since = utcnow() - timedelta(days=days)
    rows = dict(
        db.query(AIPrediction.status, func.count(AIPrediction.id))
        .filter(
            AIPrediction.tenant_id == tenant.id, AIPrediction.kind.in_(TRIAGE_KINDS), AIPrediction.created_at >= since
        )
        .group_by(AIPrediction.status)
        .all()
    )
    replies = (
        db.query(func.count(AIPrediction.id))
        .filter(
            AIPrediction.tenant_id == tenant.id,
            AIPrediction.kind == "reply",
            AIPrediction.status.in_(("accepted", "edited")),
            AIPrediction.created_at >= since,
        )
        .scalar()
    )
    kb_helpful = (
        db.query(func.count(KBQuery.id))
        .filter(KBQuery.tenant_id == tenant.id, KBQuery.helpful.is_(True), KBQuery.created_at >= since)
        .scalar()
    )
    return {
        "organization": tenant.name,
        "data_origin": tenant.data_origin,
        "is_demo": tenant.is_demo,
        "days": days,
        "triage_accepted_or_edited": rows.get("accepted", 0) + rows.get("edited", 0),
        "triage_auto_applied_kept": rows.get("auto_applied", 0),
        "triage_auto_applied_reverted": rows.get("overridden", 0),
        "reply_drafts_sent": int(replies or 0),
        "kb_answers_rated_helpful": int(kb_helpful or 0),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--org", required=True)
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--triage-minutes", type=float, required=True, help="manual minutes one triage decision takes")
    p.add_argument("--reply-minutes", type=float, required=True, help="manual minutes to write one reply")
    p.add_argument("--hourly-cost", type=float, required=True, help="loaded cost of one agent hour")
    p.add_argument("--currency", default="")
    a = p.parse_args(argv)
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.slug == a.org).first()
        if tenant is None:
            print(f"No organization with slug {a.org!r}", file=sys.stderr)
            return 2
        m = compute(db, tenant, a.days)
    finally:
        db.close()
    triage_n = m["triage_accepted_or_edited"] + m["triage_auto_applied_kept"]
    hours = (triage_n * a.triage_minutes + m["reply_drafts_sent"] * a.reply_minutes) / 60
    label = (
        ""
        if m["data_origin"] == "real" and not m["is_demo"]
        else (f"\n> **{m['data_origin'].upper()} data — not real usage. Do not quote these figures.**\n")
    )
    print(
        "\n".join(
            [
                f"# Value estimate — {m['organization']}, last {a.days} days",
                label,
                "| Measured (database) | Count |",
                "|---|---|",
                f"| Triage/routing recommendations accepted or edited by agents | {m['triage_accepted_or_edited']} |",
                f"| Changes applied automatically and not reverted | {m['triage_auto_applied_kept']} |",
                f"| Automatic changes a person reverted (excluded) | {m['triage_auto_applied_reverted']} |",
                f"| Reply drafts sent | {m['reply_drafts_sent']} |",
                f"| Knowledge-base answers rated helpful (not converted to time) | {m['kb_answers_rated_helpful']} |",
                "",
                "| Assumption (supplied by you) | Value |",
                "|---|---|",
                f"| Manual minutes per triage decision | {a.triage_minutes} |",
                f"| Manual minutes per reply | {a.reply_minutes} |",
                f"| Loaded cost per agent hour | {a.hourly_cost} {a.currency} |",
                "",
                f"**Estimate:** {hours:.1f} agent-hours of triage and drafting were prepared by the AI and "
                f"accepted by people ≈ {hours * a.hourly_cost:,.0f} {a.currency} at your assumptions. This is "
                "work *handled with AI assistance*, not a measured saving: agents still reviewed each item, and "
                "the minutes per item are your estimate. Measure the saving with the before/after comparison in "
                "docs/pilot_plan.md.",
            ]
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
