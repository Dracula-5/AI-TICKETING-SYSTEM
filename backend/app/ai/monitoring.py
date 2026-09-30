"""
AI monitoring (P13): is the model still seeing the kind of tickets it learned
from, and are people still agreeing with it?

For one organization, compare the most recent window (default 7 days) with the
preceding baseline window (default 28 days):

* **Category drift** — Population Stability Index over the category mix of
  new tickets. Rule of thumb: < 0.1 stable, 0.1–0.25 moderate, > 0.25 major.
* **Embedding drift** — cosine distance between the mean embedding of recent
  and baseline tickets.
* **Novelty rate** — share of recent tickets whose nearest resolved neighbour
  is below the triage similarity floor, i.e. tickets the AI has nothing to
  compare with (it falls back to rules for these).
* **Human agreement** — acceptance rate of decided recommendations, recent vs
  baseline.

Results are stored in `ai_monitoring` (one row per organization per run) and
surfaced in the AI performance report. Nothing here is a model-quality claim;
these are early-warning signals that trigger an offline re-evaluation.
"""

import math
from collections import Counter
from datetime import timedelta

import numpy as np
from sqlalchemy.orm import Session

from app.ai import triage
from app.db.database import utcnow
from app.db.models import AIMonitoringRun, AIPrediction, Tenant, Ticket, TicketEmbedding

MIN_TICKETS = 20  # per window; below this the signal is reported as insufficient data
PSI_WARN, PSI_ALERT = 0.1, 0.25
EPS = 1e-4


def psi(recent: Counter, baseline: Counter) -> float:
    cats = set(recent) | set(baseline)
    r_total, b_total = sum(recent.values()), sum(baseline.values())
    value = 0.0
    for c in cats:
        r = max(recent.get(c, 0) / r_total, EPS)
        b = max(baseline.get(c, 0) / b_total, EPS)
        value += (r - b) * math.log(r / b)
    return value


def _acceptance(db: Session, tenant_id: int, start, end) -> tuple[float | None, int]:
    rows = (
        db.query(AIPrediction.status)
        .filter(
            AIPrediction.tenant_id == tenant_id,
            AIPrediction.decided_at >= start,
            AIPrediction.decided_at < end,
            AIPrediction.status.in_(("accepted", "edited", "rejected")),
        )
        .all()
    )
    n = len(rows)
    return (sum(1 for (s,) in rows if s == "accepted") / n if n >= MIN_TICKETS else None), n


def run(db: Session, tenant: Tenant, recent_days: int = 7, baseline_days: int = 28) -> AIMonitoringRun:
    now = utcnow()
    recent_start = now - timedelta(days=recent_days)
    base_start = recent_start - timedelta(days=baseline_days)

    def tickets(start, end):
        return (
            db.query(Ticket)
            .filter(
                Ticket.tenant_id == tenant.id,
                Ticket.created_at >= start,
                Ticket.created_at < end,
                Ticket.channel != "import",
            )
            .all()
        )

    recent, baseline = tickets(recent_start, now), tickets(base_start, recent_start)
    metrics: dict = {
        "recent_tickets": len(recent),
        "baseline_tickets": len(baseline),
        "recent_days": recent_days,
        "baseline_days": baseline_days,
    }
    enough = len(recent) >= MIN_TICKETS and len(baseline) >= MIN_TICKETS

    if enough:
        metrics["category_psi"] = round(
            psi(Counter(t.category or "none" for t in recent), Counter(t.category or "none" for t in baseline)), 4
        )
        vecs = {
            e.ticket_id: e.embedding
            for e in db.query(TicketEmbedding).filter(TicketEmbedding.ticket_id.in_([t.id for t in recent + baseline]))
        }
        r = [vecs[t.id] for t in recent if t.id in vecs]
        b = [vecs[t.id] for t in baseline if t.id in vecs]
        if len(r) >= MIN_TICKETS and len(b) >= MIN_TICKETS:
            rc, bc = np.mean(np.asarray(r, dtype=np.float32), 0), np.mean(np.asarray(b, dtype=np.float32), 0)
            cos = float(rc @ bc / max(np.linalg.norm(rc) * np.linalg.norm(bc), 1e-12))
            metrics["embedding_centroid_distance"] = round(1 - cos, 4)
        # Novelty: recent tickets whose recorded analysis found no neighbour above the floor.
        analysed = (
            db.query(AIPrediction)
            .filter(
                AIPrediction.tenant_id == tenant.id,
                AIPrediction.ticket_id.in_([t.id for t in recent]),
                AIPrediction.kind == "next_action",
            )
            .count()
        )
        with_votes = (
            db.query(AIPrediction.ticket_id)
            .filter(
                AIPrediction.tenant_id == tenant.id,
                AIPrediction.ticket_id.in_([t.id for t in recent]),
                AIPrediction.kind == "category",
            )
            .distinct()
            .count()
        )
        if analysed:
            metrics["novelty_rate"] = round(1 - with_votes / analysed, 4)
    acc_recent, n_recent = _acceptance(db, tenant.id, recent_start, now)
    acc_base, n_base = _acceptance(db, tenant.id, base_start, recent_start)
    metrics.update(
        acceptance_recent=acc_recent, acceptance_baseline=acc_base, decisions_recent=n_recent, decisions_baseline=n_base
    )

    alerts = []
    if metrics.get("category_psi", 0) > PSI_ALERT:
        alerts.append(f"category mix shifted (PSI {metrics['category_psi']:.2f} > {PSI_ALERT})")
    elif metrics.get("category_psi", 0) > PSI_WARN:
        alerts.append(f"category mix drifting (PSI {metrics['category_psi']:.2f})")
    if metrics.get("novelty_rate", 0) > 0.5:
        alerts.append(f"{metrics['novelty_rate']:.0%} of new tickets have no similar resolved ticket")
    if acc_recent is not None and acc_base is not None and acc_base - acc_recent > 0.15:
        alerts.append(f"acceptance fell from {acc_base:.0%} to {acc_recent:.0%}")
    status = "insufficient_data" if not enough else ("alert" if alerts else "ok")
    row = AIMonitoringRun(
        tenant_id=tenant.id, status=status, metrics=metrics, alerts=alerts, engine_version=triage.ENGINE_VERSION
    )
    db.add(row)
    db.flush()
    return row
