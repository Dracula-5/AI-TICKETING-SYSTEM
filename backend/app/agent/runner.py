"""
The triage agent: plan → validate → decide → execute → verify → record.

Planner: a deterministic playbook (`PLANNER`). It gathers evidence with read
tools (similar resolved tickets, SLA statistics, knowledge-base articles) and
proposes actions as typed tool calls. No LLM plans actions here: without a
configured provider an LLM planner could not be evaluated, and every other
step below is what makes any planner safe to run.

For every proposed action:
1. schema validation (Pydantic) — malformed → `invalid`
2. domain validation (the change must be legal for this ticket/org) —
   illegal → `invalid`; already true → `no_change`
3. policy (`app.ai.policy.decide`) — risk level × org settings × confidence
4. low/medium risk + allowed → executed inside a SAVEPOINT through the same
   code path as a human "accept", then **verified** by re-reading the ticket;
   verification failure rolls the step back (`failed_verification`)
5. everything else stays `proposed` — the approval queue (P8)

The run (plan, per-step outcome, reasons, timings) is stored in `agent_runs`.
"""

import hashlib
import time

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agent.tools import KIND_TO_TOOL, ToolContext
from app.ai import decisions, policy, triage
from app.ai.embedder import get_embedder, ticket_text
from app.core import metrics
from app.db.database import utcnow
from app.db.models import AgentRun, AIPrediction, Tenant, Ticket, User
from app.kb.answer import relevant
from app.kb.search import search as kb_search

PLANNER = "triage-playbook-1"
SHORT_DESCRIPTION_WORDS = 12
ESCALATE_MIN_WINDOW_USED = 0.25
ESCALATE_MARGIN = 0.15

REQUEST_INFO_TEXT = (
    "Thanks for reaching out. So we can route this quickly, could you add: what you were trying to do, the exact "
    "error message (a screenshot helps), when it started, and whether anyone else is affected?"
)


def _kb_reply(db: Session, ticket: Ticket) -> triage.Suggestion | None:
    """A templated reply pointing the requester at a *published* article."""
    result = kb_search(db, ticket.tenant_id, f"{ticket.title}\n{ticket.description[:1000]}", k=3, public_only=True)
    hits = [h for h in result.hits if relevant(h)]
    if not hits:
        return None
    top = hits[0]
    requester = db.get(User, ticket.created_by_user_id)
    first = (requester.name.split()[0] if requester and requester.name else "there")[:40]
    section = f" (section “{top.heading}”)" if top.heading and top.heading != top.title else ""
    text = (
        f"Hi {first},\n\nThis help article may resolve it: “{top.title}”{section}. You can open it from Help "
        "articles in the portal. Could you try the steps there and let us know whether the problem persists?"
    )
    return triage.Suggestion(
        "reply",
        {"text": text},
        None,
        {
            "method": "template + knowledge-base search",
            "article": {"document_id": top.document_id, "chunk_id": top.chunk_id, "title": top.title},
        },
        source="rules",
    )


def _escalation_warranted(risk: dict, priority: str) -> bool:
    """At creation the conditional risk equals the priority's base rate, so proposing escalation
    then is noise (P5 replay: it fired on 39% of tickets). Require the ticket to be a quarter of
    the way into its window and clearly riskier than a typical ticket of its priority."""
    p, base = risk.get("breach_probability", 0.0), risk.get("base_rate", 1.0)
    return (
        priority in ("critical", "high")
        and risk.get("window_used", 0.0) >= ESCALATE_MIN_WINDOW_USED
        and p >= max(0.5, base + ESCALATE_MARGIN)
    )


def plan(db: Session, ticket: Ticket, embedder) -> list[triage.Suggestion]:
    suggestions = triage.analyze(db, ticket, embedder)
    kinds = {s.kind: s for s in suggestions}
    if ticket.status not in ("resolved", "closed"):
        reply = _kb_reply(db, ticket)
        if reply is not None:
            suggestions.append(reply)
        category = kinds.get("category")
        if len(ticket.description.split()) < SHORT_DESCRIPTION_WORDS and (
            category is None or (category.confidence or 0) < 0.5
        ):
            suggestions.append(
                triage.Suggestion(
                    "request_info",
                    {"message": REQUEST_INFO_TEXT},
                    None,
                    {"method": f"rule: description under {SHORT_DESCRIPTION_WORDS} words and no confident category"},
                    source="rules",
                )
            )
        risk = kinds.get("sla_risk")
        if risk is not None and _escalation_warranted(risk.value, ticket.priority):
            p = risk.value["breach_probability"]
            suggestions.append(
                triage.Suggestion(
                    "escalate",
                    {"reason": f"Predicted resolution-SLA breach risk {p:.0%} for a {ticket.priority} ticket"},
                    p,
                    {"method": "rule on SLA-risk statistics", "sla_risk": risk.evidence},
                    source="statistics",
                )
            )
    return suggestions


def _execute(db: Session, ctx: ToolContext, pred: AIPrediction) -> tuple[str, str]:
    spec = KIND_TO_TOOL[pred.kind]
    try:
        args = spec.input_model.model_validate(pred.value)
    except ValidationError as e:
        return "invalid", f"schema: {e.errors()[0]['msg']}"
    problem = spec.validate(ctx, args)
    if problem == "already set" or (problem and problem.startswith("already")):
        return "no_change", problem
    if problem:
        return "invalid", problem
    verdict = policy.decide(ctx.tenant, pred.kind, pred.confidence)
    if not verdict.auto_apply:
        return "proposed", verdict.reason
    savepoint = db.begin_nested()
    try:
        decisions._apply(db, ctx.ticket, pred, pred.value, actor=None)
        db.flush()
        if spec.verify is not None and not spec.verify(ctx, args):
            savepoint.rollback()
            return "failed_verification", "the ticket did not change as intended; rolled back"
    except decisions.DecisionError as e:
        savepoint.rollback()
        return "proposed", f"automatic application failed ({e.message}); left for a person"
    savepoint.commit()
    return "auto_applied", verdict.reason


def run(db: Session, ticket: Ticket, trigger: str = "ticket_created") -> AgentRun | None:
    embedder = get_embedder()
    tenant = db.get(Tenant, ticket.tenant_id)
    if embedder is None or tenant is None:
        return None
    started = time.perf_counter()
    suggestions = plan(db, ticket, embedder)
    plan_ms = (time.perf_counter() - started) * 1000
    preds = triage.record(db, ticket, suggestions, embedder.name, plan_ms)
    ctx = ToolContext(db, ticket, tenant)
    steps = []
    for pred in preds:
        step = {"kind": pred.kind, "prediction_id": pred.id, "source": pred.source, "confidence": pred.confidence}
        if pred.kind not in KIND_TO_TOOL:
            steps.append({**step, "tool": None, "outcome": "recorded"})
            continue
        t0 = time.perf_counter()
        outcome, reason = _execute(db, ctx, pred)
        if outcome == "auto_applied":
            pred.status, pred.decided_at = "auto_applied", utcnow()
        elif outcome in ("invalid", "no_change", "failed_verification"):
            pred.status = outcome
        pred.evidence = {**(pred.evidence or {}), "policy": reason}
        steps.append(
            {
                **step,
                "tool": KIND_TO_TOOL[pred.kind].name,
                "risk": KIND_TO_TOOL[pred.kind].risk,
                "outcome": outcome,
                "reason": reason,
                "ms": round((time.perf_counter() - t0) * 1000, 1),
            }
        )
    agent_run = AgentRun(
        tenant_id=ticket.tenant_id,
        ticket_id=ticket.id,
        trigger=trigger,
        planner=PLANNER,
        model=embedder.name,
        status="completed",
        steps=steps,
        latency_ms=round((time.perf_counter() - started) * 1000, 1),
        input_sha256=hashlib.sha256(ticket_text(ticket.title, ticket.description).encode()).hexdigest(),
    )
    db.add(agent_run)
    db.flush()
    metrics.AGENT_RUN.observe((agent_run.latency_ms or 0.0) / 1000)
    for step in steps:
        metrics.AI_STEPS.labels(step["kind"], step["outcome"]).inc()
    return agent_run
