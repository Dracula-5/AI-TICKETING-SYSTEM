"""
Pilot metrics (P9): what real people did with NexaDesk over a window.

Computed only from the database — never entered by hand — and scoped to one
organization. `data_origin` is reported alongside so demo or synthetic
activity is never presented as real usage. Every metric states its sample
size; a rate over fewer than MIN_SAMPLE observations is returned as None
("not enough data") rather than as a misleading percentage.
"""

from datetime import timedelta
from statistics import median

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import utcnow
from app.db.models import AIPrediction, Feedback, KBQuery, Tenant, Ticket, User

MIN_SAMPLE = 5
DECIDED = ("accepted", "edited", "rejected")


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 3) if den >= MIN_SAMPLE else None


def compute(db: Session, tenant: Tenant, days: int = 30) -> dict:
    since = utcnow() - timedelta(days=days)
    tid = tenant.id

    users = db.query(User).filter(User.tenant_id == tid, User.is_active.is_(True)).all()
    active = [u for u in users if u.last_login_at is not None and u.last_login_at >= since]
    by_role: dict[str, int] = {}
    for u in active:
        by_role[u.role] = by_role.get(u.role, 0) + 1

    tickets = (
        db.query(Ticket).filter(Ticket.tenant_id == tid, Ticket.created_at >= since, Ticket.channel != "import").all()
    )
    # Baseline: resolved history imported from the previous tool (different tool and period).
    imported = [
        (t.resolved_at - t.created_at).total_seconds() / 3600
        for t in db.query(Ticket).filter(Ticket.tenant_id == tid, Ticket.channel == "import")
        if t.resolved_at is not None
    ]
    first_response = [
        (t.first_responded_at - t.created_at).total_seconds() / 60 for t in tickets if t.first_responded_at
    ]
    resolution = [(t.resolved_at - t.created_at).total_seconds() / 3600 for t in tickets if t.resolved_at]
    breached = sum(1 for t in tickets if t.resolution_breached_at is not None)

    preds = (
        db.query(AIPrediction.status, func.count(AIPrediction.id))
        .filter(AIPrediction.tenant_id == tid, AIPrediction.created_at >= since)
        .group_by(AIPrediction.status)
        .all()
    )
    pc = dict(preds)
    decided = sum(pc.get(s, 0) for s in DECIDED)
    auto = pc.get("auto_applied", 0) + pc.get("overridden", 0)

    csat = [
        f.rating
        for f in db.query(Feedback).filter(
            Feedback.tenant_id == tid, Feedback.kind == "csat", Feedback.created_at >= since
        )
        if f.rating is not None
    ]
    product_feedback = (
        db.query(func.count(Feedback.id))
        .filter(Feedback.tenant_id == tid, Feedback.kind == "product", Feedback.created_at >= since)
        .scalar()
    )
    kb = db.query(KBQuery).filter(KBQuery.tenant_id == tid, KBQuery.created_at >= since).all()
    kb_rated = [q for q in kb if q.helpful is not None]

    return {
        "organization": tenant.name,
        "data_origin": tenant.data_origin,
        "is_demo": tenant.is_demo,
        "window_days": days,
        "generated_at": utcnow().isoformat(),
        "min_sample_for_rates": MIN_SAMPLE,
        "people": {"active_accounts": len(users), "signed_in_during_window": len(active), "by_role": by_role},
        "tickets": {
            "created": len(tickets),
            "resolved": len(resolution),
            "median_first_response_minutes": round(median(first_response), 1) if first_response else None,
            "median_resolution_hours": round(median(resolution), 2) if resolution else None,
            "resolution_sla_breached": breached,
            "resolution_sla_breach_rate": _rate(breached, len(tickets)),
        },
        "baseline_imported_history": {
            "resolved_tickets": len(imported),
            "median_resolution_hours": round(median(imported), 2) if len(imported) >= MIN_SAMPLE else None,
        },
        "ai": {
            "recommendations": sum(v for k, v in pc.items() if k not in ("superseded", "invalid")),
            "decided_by_people": decided,
            "acceptance_rate": _rate(pc.get("accepted", 0), decided),
            "edit_rate": _rate(pc.get("edited", 0), decided),
            "rejection_rate": _rate(pc.get("rejected", 0), decided),
            "auto_applied": auto,
            "automation_false_positive_rate": _rate(pc.get("overridden", 0), auto),
        },
        "satisfaction": {
            "csat_responses": len(csat),
            "csat_mean": round(sum(csat) / len(csat), 2) if len(csat) >= MIN_SAMPLE else None,
            "csat_share_4_or_5": _rate(sum(1 for r in csat if r >= 4), len(csat)),
            "product_feedback_messages": int(product_feedback or 0),
        },
        "knowledge_base": {
            "searches_and_questions": len(kb),
            "rated": len(kb_rated),
            "helpful_rate": _rate(sum(1 for q in kb_rated if q.helpful), len(kb_rated)),
        },
    }


def to_markdown(m: dict) -> str:
    def v(x, suffix=""):
        return "not enough data" if x is None else f"{x}{suffix}"

    origin = m["data_origin"]
    warn = (
        ""
        if origin == "real" and not m["is_demo"]
        else f"\n> **This organization's data is `{origin}`{' (demo)' if m['is_demo'] else ''}. "
        "These are not real-usage results.**\n"
    )
    t, a, s, k, p = m["tickets"], m["ai"], m["satisfaction"], m["knowledge_base"], m["people"]
    return "\n".join(
        [
            f"# Pilot report — {m['organization']}",
            "",
            f"Window: last {m['window_days']} days · generated {m['generated_at']} · data origin `{origin}`. "
            f"Rates need at least {m['min_sample_for_rates']} observations. Computed by `app/services/pilot.py` "
            "from the database.",
            warn,
            "| Metric | Value |",
            "|---|---|",
            f"| Active accounts / signed in during window | {p['active_accounts']} / {p['signed_in_during_window']} |",
            f"| Tickets created / resolved | {t['created']} / {t['resolved']} |",
            f"| Median first response | {v(t['median_first_response_minutes'], ' min')} |",
            f"| Median resolution time | {v(t['median_resolution_hours'], ' h')} (previous tool, imported history: "
            f"{v(m['baseline_imported_history']['median_resolution_hours'], ' h')}, "
            f"n={m['baseline_imported_history']['resolved_tickets']}) |",
            f"| Resolution-SLA breach rate | {v(t['resolution_sla_breach_rate'])} |",
            f"| AI recommendations / decided by people | {a['recommendations']} / {a['decided_by_people']} |",
            f"| AI acceptance / edit / rejection rate | {v(a['acceptance_rate'])} / {v(a['edit_rate'])} / "
            f"{v(a['rejection_rate'])} |",
            f"| Auto-applied / automation false-positive rate | {a['auto_applied']} / "
            f"{v(a['automation_false_positive_rate'])} |",
            f"| CSAT responses / mean (1–5) / share 4–5 | {s['csat_responses']} / {v(s['csat_mean'])} / "
            f"{v(s['csat_share_4_or_5'])} |",
            f"| Product feedback messages | {s['product_feedback_messages']} |",
            f"| Knowledge-base queries / rated / helpful rate | {k['searches_and_questions']} / {k['rated']} / "
            f"{v(k['helpful_rate'])} |",
            "",
        ]
    )
