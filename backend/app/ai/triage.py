"""
AI triage: recommendations for one ticket from the organization's own history.

Method (benchmarked in experiments/knn_production.py and duplicates.py):
embed the ticket, retrieve its nearest neighbours among the org's tickets, and
    * category / priority / team — similarity-weighted vote over neighbours
      that were **resolved or closed** (their labels were confirmed by the work);
    * assignee — who resolved the most similar tickets, lightly penalized by
      current open workload;
    * possible duplicates — open or recent neighbours above a similarity threshold;
    * SLA risk — share of similar-priority resolved tickets in this org that took
      longer than this ticket's resolution SLA (empirical estimate);
    * expected resolution time — weighted median of similar resolved tickets.

Every prediction carries confidence and evidence and is stored in
ai_predictions. Whether it is auto-applied or only recommended is decided by
app/ai/policy.py (human-in-the-loop), not here. With too little history the
engine returns nothing for that field and the rules engine's triage stands.
"""

import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai import index
from app.ai.embedder import Embedder, get_embedder, ticket_text
from app.db.database import utcnow
from app.db.models import AIPrediction, SlaPolicy, Team, TeamMember, Tenant, Ticket, User
from app.services.organizations import org_setting

ENGINE_VERSION = "triage-knn-2"
K = 20
VOTE_POWER = 4.0  # weights = similarity ** power (chosen on validation in P4.1b)
MIN_SIMILARITY = 0.35
MIN_STAT_SAMPLE = 20  # resolved same-priority tickets needed for ETA / SLA-risk statistics
DONE = ("resolved", "closed")


@dataclass
class Suggestion:
    kind: str
    value: dict
    confidence: float | None
    evidence: dict = field(default_factory=dict)
    source: str = "ai"


def _vote(neighbors, labels) -> tuple[object, float, dict]:
    weights: dict = defaultdict(float)
    for n in neighbors:
        label = labels.get(n.ticket_id)
        if label is not None:
            weights[label] += max(n.similarity, 0.0) ** VOTE_POWER
    total = sum(weights.values())
    if not total:
        return None, 0.0, {}
    best = max(weights, key=lambda label: weights[label])
    return best, weights[best] / total, {str(k): round(v / total, 3) for k, v in weights.items()}


def _evidence(neighbors, tickets, limit=5) -> list[dict]:
    out = []
    for n in neighbors[:limit]:
        t = tickets.get(n.ticket_id)
        if t is not None:
            out.append(
                {
                    "ticket_id": t.id,
                    "number": t.number,
                    "title": t.title,
                    "status": t.status,
                    "similarity": round(n.similarity, 3),
                }
            )
    return out


def analyze(db: Session, ticket: Ticket, embedder: Embedder | None = None) -> list[Suggestion]:
    embedder = embedder or get_embedder()
    if embedder is None:
        return []
    tenant = db.get(Tenant, ticket.tenant_id)
    if tenant is None:
        return []
    vec = embedder.embed([ticket_text(ticket.title, ticket.description)])[0]
    index.upsert(db, ticket_id=ticket.id, tenant_id=ticket.tenant_id, model=embedder.name, vector=vec)

    neighbors = index.search(
        db, tenant_id=ticket.tenant_id, vector=vec, model=embedder.name, k=60, exclude_ticket_id=ticket.id
    )
    neighbors = [n for n in neighbors if n.similarity >= MIN_SIMILARITY]
    ids = [n.ticket_id for n in neighbors]
    tickets = (
        {t.id: t for t in db.query(Ticket).filter(Ticket.id.in_(ids), Ticket.tenant_id == ticket.tenant_id)}
        if ids
        else {}
    )
    resolved = [n for n in neighbors if tickets.get(n.ticket_id) and tickets[n.ticket_id].status in DONE][:K]
    min_history = int(org_setting(tenant, "ai_min_history"))
    out: list[Suggestion] = []

    if len(resolved) >= min_history:
        common = {"neighbors_used": len(resolved), "similar_tickets": _evidence(resolved, tickets)}
        for kind, attr in (("category", "category"), ("priority", "priority")):
            label, conf, dist = _vote(resolved, {n.ticket_id: getattr(tickets[n.ticket_id], attr) for n in resolved})
            if label is not None:
                out.append(Suggestion(kind, {kind: label}, conf, {**common, "distribution": dist}))
        team_id, conf, dist = _vote(resolved, {n.ticket_id: tickets[n.ticket_id].team_id for n in resolved})
        if team_id is not None:
            team = db.get(Team, team_id)
            if team is not None and team.tenant_id == ticket.tenant_id:
                out.append(
                    Suggestion("team", {"team_id": team.id, "team": team.name}, conf, {**common, "distribution": dist})
                )
                assignee = _recommend_assignee(db, ticket, resolved, tickets, team.id)
                if assignee:
                    out.append(assignee)

    duplicates = _duplicates(ticket, neighbors, tickets, float(org_setting(tenant, "ai_duplicate_threshold")))
    if duplicates:
        out.append(duplicates)
    durations = _priority_durations(db, ticket)
    eta = _expected_resolution(ticket, durations)
    if eta:
        out.append(eta)
    risk = _sla_risk(db, ticket, durations)
    if risk:
        out.append(risk)
    out.append(_next_best_action(ticket))
    return out


def _recommend_assignee(db, ticket, resolved, tickets, team_id) -> Suggestion | None:
    members = {uid for (uid,) in db.query(TeamMember.user_id).filter(TeamMember.team_id == team_id)}
    active = (
        {
            u.id: u
            for u in db.query(User).filter(
                User.id.in_(members), User.is_active.is_(True), User.tenant_id == ticket.tenant_id
            )
        }
        if members
        else {}
    )
    if not active:
        return None
    score: dict[int, float] = defaultdict(float)
    for n in resolved:
        uid = tickets[n.ticket_id].assigned_to_user_id
        if uid in active:
            score[uid] += max(n.similarity, 0.0) ** VOTE_POWER
    if not score:
        return None
    load = dict(
        db.query(Ticket.assigned_to_user_id, func.count(Ticket.id))
        .filter(
            Ticket.tenant_id == ticket.tenant_id,
            Ticket.assigned_to_user_id.in_(list(score)),
            Ticket.status.notin_(DONE),
        )
        .group_by(Ticket.assigned_to_user_id)
        .all()
    )
    ranked = sorted(score, key=lambda uid: score[uid] / (1 + 0.1 * load.get(uid, 0)), reverse=True)
    best = ranked[0]
    total = sum(score.values())
    return Suggestion(
        "assignee",
        {"user_id": best, "name": active[best].name},
        score[best] / total,
        {
            "reason": "Resolved the most similar tickets; adjusted for current open workload",
            "candidates": [
                {
                    "user_id": u,
                    "name": active[u].name,
                    "similar_resolved_weight": round(score[u] / total, 3),
                    "open_tickets": int(load.get(u, 0)),
                }
                for u in ranked[:3]
            ],
        },
    )


def _priority_durations(db: Session, ticket: Ticket) -> np.ndarray:
    """Minutes from creation to resolution of this org's latest resolved tickets of the same priority."""
    rows = (
        db.query(Ticket.created_at, Ticket.resolved_at)
        .filter(
            Ticket.tenant_id == ticket.tenant_id,
            Ticket.priority == ticket.priority,
            Ticket.resolved_at.isnot(None),
            Ticket.id != ticket.id,
        )
        .order_by(Ticket.resolved_at.desc())
        .limit(500)
        .all()
    )
    return np.array([(r[1] - r[0]).total_seconds() / 60 for r in rows if r[0] is not None and r[1] is not None])


def _expected_resolution(ticket: Ticket, durations: np.ndarray) -> Suggestion | None:
    """Median and inter-quartile range of this org's resolved tickets of the same priority.
    A similarity-weighted median of neighbours was measured worse than this plain statistic
    (reports/pipeline/, P5), so the simpler one ships."""
    if len(durations) < MIN_STAT_SAMPLE:
        return None
    hours = durations / 60
    q1, median, q3 = (float(np.percentile(hours, q)) for q in (25, 50, 75))
    return Suggestion(
        "resolution_time",
        {"hours": round(median, 1), "low_hours": round(q1, 1), "high_hours": round(q3, 1)},
        None,
        {
            "method": f"median of this organization's last {len(hours)} resolved {ticket.priority}-priority tickets",
            "n": len(hours),
        },
        source="statistics",
    )


def _duplicates(ticket, neighbors, tickets, threshold) -> Suggestion | None:
    recent = ticket.created_at - timedelta(days=30) if ticket.created_at else None
    candidates = []
    for n in neighbors:
        t = tickets.get(n.ticket_id)
        if t is None or n.similarity < threshold:
            continue
        if t.status not in DONE or (recent and t.created_at >= recent):
            candidates.append(
                {
                    "ticket_id": t.id,
                    "number": t.number,
                    "title": t.title,
                    "status": t.status,
                    "similarity": round(n.similarity, 3),
                    "same_requester": t.created_by_user_id == ticket.created_by_user_id,
                }
            )
    if not candidates:
        return None
    return Suggestion(
        "duplicate",
        {"ticket_id": candidates[0]["ticket_id"], "number": candidates[0]["number"]},
        candidates[0]["similarity"],
        {"candidates": candidates[:5], "threshold": threshold},
    )


def _sla_risk(db: Session, ticket: Ticket, durations: np.ndarray) -> Suggestion | None:
    policy = (
        db.query(SlaPolicy)
        .filter(SlaPolicy.tenant_id == ticket.tenant_id, SlaPolicy.priority == ticket.priority)
        .first()
    )
    if policy is None or len(durations) < MIN_STAT_SAMPLE:
        return None
    window = policy.resolution_minutes
    age = (utcnow() - ticket.created_at).total_seconds() / 60 if ticket.created_at else 0.0
    still_open = durations[durations > age]  # condition on having survived to the current age
    if len(still_open) < 10:
        return None
    p = float((still_open > window).mean())
    base = float((durations > window).mean())
    return Suggestion(
        "sla_risk",
        {
            "breach_probability": round(p, 3),
            "level": "high" if p >= 0.5 else "medium" if p >= 0.2 else "low",
            "base_rate": round(base, 3),
            "window_used": round(min(age / window, 9.99), 3),
        },
        None,
        {
            "method": "empirical: share of this org's resolved tickets of the same priority that took "
            "longer than the resolution SLA, among those still open at this ticket's age",
            "n": int(len(still_open)),
            "sla_minutes": window,
        },
        source="statistics",
    )


def _next_best_action(ticket: Ticket) -> Suggestion:
    """Deterministic checklist — labelled as a rule, not AI."""
    steps = []
    if ticket.assigned_to_user_id is None:
        steps.append("Assign an owner (see the team and assignee recommendations)")
    if ticket.first_responded_at is None:
        steps.append("Send a first response — the first-response SLA is running")
    if ticket.status == "waiting_for_customer":
        steps.append("Waiting on the requester: the SLA clock is paused")
    if ticket.priority in ("critical", "high") and ticket.status not in DONE:
        steps.append("High impact: consider escalating if it cannot be resolved quickly")
    if not steps:
        steps.append("Work the ticket and record a resolution summary when done")
    return Suggestion("next_action", {"steps": steps}, None, {"method": "rules"}, source="rules")


# Statuses a newer analysis replaces (decided ones are history and are kept).
OPEN_STATUSES = ("proposed", "no_change", "invalid", "failed_verification")


def record(
    db: Session, ticket: Ticket, suggestions: list[Suggestion], model: str, latency_ms: float
) -> list[AIPrediction]:
    """Persist suggestions, superseding older unresolved predictions of the same kind."""
    digest = hashlib.sha256(ticket_text(ticket.title, ticket.description).encode()).hexdigest()
    kinds = [s.kind for s in suggestions]
    if kinds:
        db.query(AIPrediction).filter(
            AIPrediction.ticket_id == ticket.id,
            AIPrediction.kind.in_(kinds),
            AIPrediction.status.in_(OPEN_STATUSES),
        ).update({AIPrediction.status: "superseded"}, synchronize_session=False)
    rows = []
    for s in suggestions:
        row = AIPrediction(
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            kind=s.kind,
            source=s.source,
            model=model if s.source == "ai" else s.source,
            model_version=ENGINE_VERSION,
            value=s.value,
            confidence=s.confidence,
            evidence=s.evidence,
            latency_ms=round(latency_ms, 1),
            input_sha256=digest,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def run(db: Session, ticket: Ticket) -> list[AIPrediction]:
    embedder = get_embedder()
    if embedder is None:
        return []
    started = time.perf_counter()
    suggestions = analyze(db, ticket, embedder)
    return record(db, ticket, suggestions, embedder.name, (time.perf_counter() - started) * 1000)
