"""
Applying AI suggestions — automatically (policy) or by a person (accept / edit /
reject) — and recording every outcome on the prediction row.

Auto-applied changes are made with actor_type="ai" (status history + audit
log), so an automated decision is always distinguishable from a human one.
If a person later changes a field an AI auto-applied, the prediction is
marked `overridden` — the input for the false-positive automation rate.
"""

from sqlalchemy.orm import Session

from app.core import metrics
from app.db.database import utcnow
from app.db.models import AIPrediction, Ticket, TicketComment, User
from app.services import audit
from app.services import tickets as ticket_svc


class DecisionError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _apply(db: Session, ticket: Ticket, pred: AIPrediction, value: dict, actor: User | None) -> None:
    """Make the change a prediction describes. actor=None means the AI itself."""
    actor_type = "ai" if actor is None else "user"
    reason = (
        f"AI recommendation ({pred.model}, confidence {pred.confidence:.2f})"
        if pred.confidence is not None
        else "AI recommendation"
    )
    if pred.kind in ("category", "priority"):
        field = pred.kind
        new = value.get(field)
        if new is None:
            raise DecisionError(f"value.{field} is required", 422)
        if actor is None:
            before = {field: getattr(ticket, field)}
            if field == "category" and new not in {c.name for c in ticket_svc.org_categories(db, ticket.tenant_id)}:
                raise DecisionError("Unknown category", 422)
            setattr(ticket, field, new)
            if field == "priority":
                ticket_svc.apply_sla_policy(db, ticket)
            audit.record(
                db,
                "ticket.update",
                tenant_id=ticket.tenant_id,
                actor_type="ai",
                entity_type="ticket",
                entity_id=ticket.id,
                changes={**audit.diff(before, {field: new}), "reason": reason},
            )
        else:
            try:
                ticket_svc.update_fields(db, ticket, actor=actor, fields={field: new})
            except ticket_svc.TicketError as e:
                raise DecisionError(e.message, e.status_code) from None
        ticket.triage_source = "ai"
    elif pred.kind in ("team", "assignee"):
        team_id = value.get("team_id") if pred.kind == "team" else None
        assignee_id = value.get("user_id") if pred.kind == "assignee" else ticket.assigned_to_user_id
        try:
            ticket_svc.assign(
                db, ticket, assignee_id=assignee_id, team_id=team_id, actor=actor, actor_type=actor_type, reason=reason
            )
        except ticket_svc.TicketError as e:
            raise DecisionError(e.message, e.status_code) from None
        if pred.kind == "team":
            ticket.triage_source = "ai"
    elif pred.kind == "duplicate":
        # A person confirms the link; closing the duplicate stays a separate,
        # explicit workflow action.
        other = value.get("number")
        db.add(
            TicketComment(
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.id,
                author_user_id=actor.id if actor else None,
                visibility="internal",
                content=f"Marked as a duplicate of #{other} (AI suggestion confirmed).",
            )
        )
    elif pred.kind == "reply":
        # Accepting (or editing) a draft sends it as the agent's own public reply.
        text = (value.get("text") or "").strip()
        if actor is None or not text:
            raise DecisionError("A reply draft needs a person and some text to send", 422)
        try:
            ticket_svc.add_comment(db, ticket, author=actor, content=text, visibility="public")
        except ticket_svc.TicketError as e:
            raise DecisionError(e.message, e.status_code) from None
    elif pred.kind == "request_info":
        # Ask the requester publicly. When the state machine allows it, the
        # question goes out as the "waiting for customer" transition (which
        # posts it and pauses the SLA clock); otherwise as a plain reply.
        text = (value.get("message") or "").strip()
        if actor is None or not text:
            raise DecisionError("Asking the requester needs a person and a message", 422)
        try:
            ticket_svc.check_transition(ticket, ticket_svc.TicketStatus.WAITING_FOR_CUSTOMER, actor)
            can_wait = True
        except ticket_svc.TicketError as e:
            if e.status_code == 403:
                raise DecisionError(e.message, e.status_code) from None
            can_wait = False
        try:
            if can_wait:
                ticket_svc.transition(db, ticket, "waiting_for_customer", actor=actor, reason=text)
            else:
                ticket_svc.add_comment(db, ticket, author=actor, content=text, visibility="public")
        except ticket_svc.TicketError as e:
            raise DecisionError(e.message, e.status_code) from None
    elif pred.kind == "escalate":
        if actor is None:
            raise DecisionError("Escalation needs a person to confirm it", 422)
        try:
            ticket_svc.transition(db, ticket, "escalated", actor=actor, reason=(value.get("reason") or reason)[:500])
        except ticket_svc.TicketError as e:
            raise DecisionError(e.message, e.status_code) from None
    # summary / next_action / sla_risk / resolution_time: nothing to apply
    # (accept / reject on a summary records whether it was useful).


def decide_by_human(db: Session, pred: AIPrediction, user: User, decision: str, value: dict | None) -> AIPrediction:
    if pred.status not in ("proposed", "auto_applied"):
        raise DecisionError(f"This recommendation was already {pred.status}", 409)
    ticket = db.get(Ticket, pred.ticket_id)
    if ticket is None:
        raise DecisionError("Ticket not found", 404)
    if decision == "accept":
        if pred.status == "proposed":
            _apply(db, ticket, pred, pred.value, actor=user)
        pred.status, pred.final_value = "accepted", pred.value
    elif decision == "edit":
        if not value:
            raise DecisionError("An edited value is required", 422)
        _apply(db, ticket, pred, value, actor=user)
        pred.status, pred.final_value = "edited", value
    elif decision == "reject":
        pred.status = "rejected"
    else:
        raise DecisionError("decision must be accept, edit or reject", 422)
    pred.decided_by_user_id, pred.decided_at = user.id, utcnow()
    metrics.AI_DECISIONS.labels(pred.kind, decision).inc()
    audit.record(
        db,
        f"ai.{decision}",
        tenant_id=pred.tenant_id,
        actor=user,
        entity_type="ai_prediction",
        entity_id=pred.id,
        changes={"kind": pred.kind, "ticket_id": pred.ticket_id},
    )
    return pred


FIELD_KIND = {"category": "category", "priority": "priority", "team_id": "team", "assigned_to_user_id": "assignee"}


def note_human_change(db: Session, ticket: Ticket, changed_fields: set[str], actor: User) -> None:
    """A person changed a field: open recommendations for it are superseded and
    auto-applied ones are marked overridden."""
    kinds = {FIELD_KIND[f] for f in changed_fields if f in FIELD_KIND}
    if not kinds:
        return
    now = utcnow()
    for pred in db.query(AIPrediction).filter(
        AIPrediction.ticket_id == ticket.id,
        AIPrediction.kind.in_(kinds),
        AIPrediction.status.in_(["proposed", "auto_applied"]),
    ):
        pred.status = "overridden" if pred.status == "auto_applied" else "superseded"
        pred.decided_by_user_id, pred.decided_at = actor.id, now
