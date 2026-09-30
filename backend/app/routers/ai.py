"""
AI endpoints (staff only — requesters never see model internals).

GET  /tickets/{id}/ai                  current recommendations + triage status
POST /tickets/{id}/ai/analyze          run analysis now (synchronous)
POST /tickets/{id}/classify            alias: analysis, category/priority subset
POST /tickets/{id}/route               alias: analysis, team/assignee subset
POST /ai/predictions/{id}/decision     accept | edit | reject
GET  /analytics/ai-performance         acceptance / override / automation metrics
GET  /ai/capabilities                  which AI features are configured
POST /tickets/{id}/ai/summary          generate a staff summary (LLM)
POST /tickets/{id}/ai/reply-draft      draft a reply for the agent to edit/send (LLM)
"""

from datetime import datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.agent import runner
from app.ai import decisions, generative, llm
from app.ai.embedder import get_embedder
from app.ai.policy import RISK
from app.core.config import settings
from app.core.deps import get_org_user, org_id, require_permission
from app.core.limiter import limiter
from app.core.rbac import P, can_read_all_tickets, has_permission
from app.db.database import get_db, utcnow
from app.db.models import AgentRun, AIMonitoringRun, AIPrediction, Job, LLMCall, Tenant, Ticket, User
from app.services import tickets as ticket_svc
from app.services.organizations import org_setting

router = APIRouter(tags=["ai"])


class PredictionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    source: str
    model: str
    model_version: str
    value: dict[str, Any]
    confidence: float | None
    evidence: dict[str, Any] | None
    latency_ms: float | None
    status: str
    final_value: dict[str, Any] | None
    decided_at: datetime | None
    created_at: datetime


class TicketAIOut(BaseModel):
    status: Literal["disabled", "pending", "ready", "failed"]
    model: str | None
    predictions: list[PredictionOut]


class DecisionIn(BaseModel):
    decision: Literal["accept", "edit", "reject"]
    value: dict[str, Any] | None = None


def _staff_ticket(db: Session, ticket_id: int, user: User):
    if not can_read_all_tickets(user.role):
        raise HTTPException(status_code=403, detail="AI recommendations are available to support staff")
    try:
        return ticket_svc.get_visible_ticket(db, ticket_id, user)
    except ticket_svc.TicketError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from None


# Replaced by a newer analysis, or never valid: kept for audit and metrics, not shown.
HIDDEN_STATUSES = ("superseded", "invalid", "failed_verification")


def _current(db: Session, ticket_id: int) -> list[AIPrediction]:
    return (
        db.query(AIPrediction)
        .filter(AIPrediction.ticket_id == ticket_id, AIPrediction.status.notin_(HIDDEN_STATUSES))
        .order_by(AIPrediction.created_at.desc(), AIPrediction.id.desc())
        .all()
    )


@router.get("/tickets/{ticket_id}/ai", response_model=TicketAIOut)
def ticket_ai(ticket_id: int, user: User = Depends(get_org_user), db: Session = Depends(get_db)):
    ticket = _staff_ticket(db, ticket_id, user)
    preds = _current(db, ticket.id)
    status: Literal["disabled", "pending", "ready", "failed"]
    if not settings.ai_enabled:
        status = "disabled"
    elif preds:
        status = "ready"
    else:
        job = db.query(Job).filter(Job.dedupe_key == f"ai.triage:{ticket.id}").order_by(Job.id.desc()).first()
        status = (
            "failed"
            if job is not None and job.status == "dead"
            else "pending"
            if job is not None and job.status != "done"
            else "ready"
        )
    return TicketAIOut(
        status=status,
        model=settings.embedding_model if settings.ai_enabled else None,
        predictions=[PredictionOut.model_validate(p) for p in preds],
    )


def _analyze(db: Session, ticket_id: int, user: User, kinds: set[str] | None) -> TicketAIOut:
    if not has_permission(user.role, P.TICKETS_WORK):
        raise HTTPException(status_code=403, detail="Only support staff can run AI analysis")
    ticket = _staff_ticket(db, ticket_id, user)
    if get_embedder() is None:
        raise HTTPException(status_code=503, detail="AI is not available; the rules engine is handling triage")
    runner.run(db, ticket, trigger="manual")
    db.commit()
    shown = [p for p in _current(db, ticket.id) if kinds is None or p.kind in kinds]
    return TicketAIOut(
        status="ready", model=settings.embedding_model, predictions=[PredictionOut.model_validate(p) for p in shown]
    )


@router.post("/tickets/{ticket_id}/ai/analyze", response_model=TicketAIOut)
def analyze(ticket_id: int, user: User = Depends(get_org_user), db: Session = Depends(get_db)):
    return _analyze(db, ticket_id, user, None)


@router.post("/tickets/{ticket_id}/classify", response_model=TicketAIOut)
def classify(ticket_id: int, user: User = Depends(get_org_user), db: Session = Depends(get_db)):
    return _analyze(db, ticket_id, user, {"category", "priority"})


@router.post("/tickets/{ticket_id}/route", response_model=TicketAIOut)
def route(ticket_id: int, user: User = Depends(get_org_user), db: Session = Depends(get_db)):
    return _analyze(db, ticket_id, user, {"team", "assignee"})


class CapabilitiesOut(BaseModel):
    triage: bool
    embedding_model: str | None
    text_generation: bool
    llm_provider: str | None
    llm_model: str | None


@router.get("/ai/capabilities", response_model=CapabilitiesOut)
def capabilities(user: User = Depends(get_org_user)):
    provider = llm.get_llm()
    return CapabilitiesOut(
        triage=settings.ai_enabled,
        embedding_model=settings.embedding_model if settings.ai_enabled else None,
        text_generation=provider is not None,
        llm_provider=provider.name if provider else None,
        llm_model=provider.model if provider else None,
    )


def _generate(db: Session, ticket_id: int, user: User, kind: str) -> PredictionOut:
    if not has_permission(user.role, P.TICKETS_WORK):
        raise HTTPException(status_code=403, detail="Only support staff can use AI text generation")
    ticket = _staff_ticket(db, ticket_id, user)
    provider = llm.get_llm()
    if provider is None:
        raise HTTPException(status_code=503, detail="Text generation is not configured for this deployment")
    try:
        fn = generative.summarize if kind == "summary" else generative.draft_reply
        pred = fn(db, ticket, user, provider)
    except llm.LLMError as e:
        db.commit()  # keep the ledger row of the failed call
        raise HTTPException(status_code=e.status_code, detail=e.message) from None
    db.commit()
    db.refresh(pred)
    return PredictionOut.model_validate(pred)


@router.post("/tickets/{ticket_id}/ai/summary", response_model=PredictionOut)
@limiter.limit("20/minute")
def summary(request: Request, ticket_id: int, user: User = Depends(get_org_user), db: Session = Depends(get_db)):
    return _generate(db, ticket_id, user, "summary")


@router.post("/tickets/{ticket_id}/ai/reply-draft", response_model=PredictionOut)
@limiter.limit("20/minute")
def reply_draft(request: Request, ticket_id: int, user: User = Depends(get_org_user), db: Session = Depends(get_db)):
    return _generate(db, ticket_id, user, "reply")


@router.post("/ai/predictions/{prediction_id}/decision", response_model=PredictionOut)
def decide(
    prediction_id: int,
    payload: DecisionIn,
    user: User = Depends(require_permission(P.TICKETS_WORK)),
    db: Session = Depends(get_db),
):
    pred = (
        db.query(AIPrediction).filter(AIPrediction.id == prediction_id, AIPrediction.tenant_id == org_id(user)).first()
    )
    if pred is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    _staff_ticket(db, pred.ticket_id, user)
    kind_needs_assign = pred.kind in ("team", "assignee") and payload.decision != "reject"
    if kind_needs_assign and not has_permission(user.role, P.TICKETS_ASSIGN):
        target = (payload.value or pred.value).get("user_id")
        if pred.kind == "team" or target != user.id:
            raise HTTPException(status_code=403, detail="Only managers can route tickets to other teams or people")
    try:
        decisions.decide_by_human(db, pred, user, payload.decision, payload.value)
    except decisions.DecisionError as e:
        db.rollback()
        raise HTTPException(status_code=e.status_code, detail=e.message) from None
    db.commit()
    db.refresh(pred)
    return pred


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trigger: str
    planner: str
    model: str
    status: str
    steps: list[dict[str, Any]]
    latency_ms: float | None
    created_at: datetime


@router.get("/tickets/{ticket_id}/agent/runs", response_model=list[AgentRunOut])
def agent_runs(ticket_id: int, user: User = Depends(get_org_user), db: Session = Depends(get_db)):
    ticket = _staff_ticket(db, ticket_id, user)
    return db.query(AgentRun).filter(AgentRun.ticket_id == ticket.id).order_by(AgentRun.id.desc()).limit(20).all()


class QueueItem(BaseModel):
    prediction: PredictionOut
    risk: str
    ticket_id: int
    ticket_number: int
    ticket_title: str
    ticket_status: str
    ticket_priority: str


class QueueOut(BaseModel):
    items: list[QueueItem]
    total: int
    by_risk: dict[str, int]


ACTIONABLE_KINDS = ("category", "priority", "team", "assignee", "duplicate", "reply", "request_info", "escalate")


@router.get("/ai/queue", response_model=QueueOut)
def approval_queue(
    risk: Literal["low", "medium", "high"] | None = None,
    kind: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(require_permission(P.TICKETS_WORK)),
    db: Session = Depends(get_db),
):
    """Recommendations waiting for a person, across the organization's open tickets."""
    kinds = [k for k in ACTIONABLE_KINDS if (kind is None or k == kind) and (risk is None or RISK.get(k) == risk)]
    q = (
        db.query(AIPrediction, Ticket)
        .join(Ticket, Ticket.id == AIPrediction.ticket_id)
        .filter(
            AIPrediction.tenant_id == org_id(user),
            AIPrediction.status == "proposed",
            AIPrediction.kind.in_(kinds),
            Ticket.status.notin_(("resolved", "closed")),
        )
    )
    counts = dict(q.with_entities(AIPrediction.kind, func.count(AIPrediction.id)).group_by(AIPrediction.kind).all())
    by_risk: dict[str, int] = {}
    for k, n in counts.items():
        by_risk[RISK.get(k, "high")] = by_risk.get(RISK.get(k, "high"), 0) + n
    rows = q.order_by(AIPrediction.created_at.asc()).limit(limit).all()
    return QueueOut(
        items=[
            QueueItem(
                prediction=PredictionOut.model_validate(p),
                risk=RISK.get(p.kind, "high"),
                ticket_id=t.id,
                ticket_number=t.number,
                ticket_title=t.title,
                ticket_status=t.status,
                ticket_priority=t.priority,
            )
            for p, t in rows
        ],
        total=sum(counts.values()),
        by_risk=by_risk,
    )


class BulkDecisionIn(BaseModel):
    prediction_ids: list[int] = Field(min_length=1, max_length=100)
    decision: Literal["accept", "reject"]


class BulkDecisionOut(BaseModel):
    decided: list[int]
    failed: dict[int, str]


@router.post("/ai/predictions/bulk-decision", response_model=BulkDecisionOut)
def bulk_decision(
    payload: BulkDecisionIn, user: User = Depends(require_permission(P.TICKETS_WORK)), db: Session = Depends(get_db)
):
    """Accept or reject several recommendations; each is decided independently
    with the same permission checks as a single decision."""
    decided, failed = [], {}
    for pid in dict.fromkeys(payload.prediction_ids):
        try:
            decide(pid, DecisionIn(decision=payload.decision), user, db)
            decided.append(pid)
        except HTTPException as e:
            db.rollback()
            failed[pid] = str(e.detail)
    return BulkDecisionOut(decided=decided, failed=failed)


class KindStats(BaseModel):
    kind: str
    total: int
    auto_applied: int
    accepted: int
    edited: int
    rejected: int
    overridden: int
    pending: int
    no_change: int
    invalid: int
    failed_verification: int
    acceptance_rate: float | None
    override_rate: float | None
    automation_false_positive_rate: float | None
    mean_confidence: float | None


class LLMUsage(BaseModel):
    calls: int
    failed_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    p50_latency_ms: float | None
    tokens_this_month: int
    monthly_token_budget: int


class AIPerformanceOut(BaseModel):
    window_days: int
    data_origin: str
    tickets_analyzed: int
    p50_latency_ms: float | None
    p95_latency_ms: float | None
    models: dict[str, int]
    by_kind: list[KindStats]
    text_generation: LLMUsage
    definitions: dict[str, str]


@router.get("/analytics/ai-performance", response_model=AIPerformanceOut)
def ai_performance(
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(require_permission(P.ANALYTICS_READ)),
    db: Session = Depends(get_db),
):
    tid = org_id(user)
    since = utcnow() - timedelta(days=days)
    base = db.query(AIPrediction).filter(AIPrediction.tenant_id == tid, AIPrediction.created_at >= since)
    rows = (
        base.with_entities(
            AIPrediction.kind, AIPrediction.status, func.count(AIPrediction.id), func.avg(AIPrediction.confidence)
        )
        .group_by(AIPrediction.kind, AIPrediction.status)
        .all()
    )
    stats: dict[str, dict] = {}
    for kind, status, count, conf in rows:
        s = stats.setdefault(kind, {"kind": kind, "counts": {}, "conf": []})
        s["counts"][status] = count
        if conf is not None:
            s["conf"].append((conf, count))
    by_kind = []
    for kind, s in sorted(stats.items()):
        c = s["counts"]
        accepted, edited, rejected = c.get("accepted", 0), c.get("edited", 0), c.get("rejected", 0)
        auto, overridden = c.get("auto_applied", 0), c.get("overridden", 0)
        decided = accepted + edited + rejected
        total = sum(v for k, v in c.items() if k not in ("superseded", "invalid"))
        conf_n = sum(n for _, n in s["conf"])
        by_kind.append(
            KindStats(
                kind=kind,
                total=total,
                auto_applied=auto,
                accepted=accepted,
                edited=edited,
                rejected=rejected,
                overridden=overridden,
                pending=c.get("proposed", 0),
                no_change=c.get("no_change", 0),
                invalid=c.get("invalid", 0),
                failed_verification=c.get("failed_verification", 0),
                acceptance_rate=round(accepted / decided, 3) if decided else None,
                override_rate=round((edited + rejected) / decided, 3) if decided else None,
                automation_false_positive_rate=round(overridden / (auto + overridden), 3)
                if auto + overridden
                else None,
                mean_confidence=round(sum(v * n for v, n in s["conf"]) / conf_n, 3) if conf_n else None,
            )
        )
    # One latency per analysis run (all predictions of a run share it).
    latencies = sorted(
        x
        for (x,) in base.filter(AIPrediction.latency_ms.isnot(None))
        .with_entities(func.max(AIPrediction.latency_ms))
        .group_by(AIPrediction.ticket_id, AIPrediction.created_at)
    )
    tenant = db.get(Tenant, tid)
    calls = db.query(LLMCall).filter(LLMCall.tenant_id == tid, LLMCall.created_at >= since).all()
    costs = [c.cost_usd for c in calls if c.status == "ok"]
    call_lat = sorted(c.latency_ms for c in calls if c.latency_ms is not None)
    usage = LLMUsage(
        calls=len(calls),
        failed_calls=sum(1 for c in calls if c.status != "ok"),
        input_tokens=sum(c.input_tokens for c in calls),
        output_tokens=sum(c.output_tokens for c in calls),
        cost_usd=round(sum(c for c in costs if c is not None), 4)
        if costs and all(c is not None for c in costs)
        else None,
        p50_latency_ms=call_lat[len(call_lat) // 2] if call_lat else None,
        tokens_this_month=llm.tokens_used_this_month(db, tid),
        monthly_token_budget=int(org_setting(tenant, "ai_llm_monthly_token_budget")) if tenant else 0,
    )
    return AIPerformanceOut(
        window_days=days,
        data_origin=tenant.data_origin if tenant else "real",
        tickets_analyzed=base.with_entities(func.count(func.distinct(AIPrediction.ticket_id))).scalar() or 0,
        p50_latency_ms=latencies[len(latencies) // 2] if latencies else None,
        p95_latency_ms=latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else None,
        models=dict(
            base.filter(AIPrediction.source == "ai")
            .with_entities(AIPrediction.model, func.count(AIPrediction.id))
            .group_by(AIPrediction.model)
            .all()
        ),
        by_kind=by_kind,
        text_generation=usage,
        definitions={
            "acceptance_rate": "accepted / (accepted + edited + rejected) among recommendations a person decided",
            "override_rate": "(edited + rejected) / decided",
            "automation_false_positive_rate": "auto-applied changes a person later reverted / all auto-applied",
            "latency": "per analysis run (embedding + retrieval + voting), measured in the worker",
            "cost_usd": "sum over successful text-generation calls at the configured per-token prices; "
            "empty when prices are not configured",
        },
    )


class MonitoringRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    metrics: dict[str, Any]
    alerts: list[str]
    engine_version: str
    created_at: datetime


@router.get("/analytics/ai-monitoring", response_model=list[MonitoringRunOut])
def ai_monitoring(user: User = Depends(require_permission(P.ANALYTICS_READ)), db: Session = Depends(get_db)):
    """Recent drift / agreement checks for this organization, newest first."""
    return (
        db.query(AIMonitoringRun)
        .filter(AIMonitoringRun.tenant_id == org_id(user))
        .order_by(AIMonitoringRun.id.desc())
        .limit(30)
        .all()
    )
