"""
Typed tools the triage agent may use. Each tool declares:

* an input schema (Pydantic) — malformed arguments never reach the database;
* a risk level — read (run immediately), low / medium (may run automatically
  when the organization's policy allows and confidence is high enough), high
  (always waits for a person);
* a domain validator — the proposed change must be legal *for this ticket in
  this organization* (category exists, team belongs to the org, the state
  machine allows the transition, …);
* a verifier — after an automatic change, re-read the ticket and confirm the
  database now says what the tool intended.

Execution itself goes through `app.ai.decisions._apply`, the same code path a
person's "accept" uses, so an agent can never do something a human approval
could not.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.rbac import ASSIGNABLE_ROLES
from app.db.models import Team, Tenant, Ticket, User
from app.services import tickets as ticket_svc
from app.services.tickets import TicketStatus

Risk = Literal["read", "low", "medium", "high"]


@dataclass
class ToolContext:
    db: Session
    ticket: Ticket
    tenant: Tenant


class SetCategory(BaseModel):
    category: str = Field(min_length=1, max_length=80)


class SetPriority(BaseModel):
    priority: Literal["critical", "high", "medium", "low"]


class RouteTeam(BaseModel):
    team_id: int
    team: str | None = None


class AssignAgent(BaseModel):
    user_id: int
    name: str | None = None


class LinkDuplicate(BaseModel):
    ticket_id: int
    number: int


class SendReply(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class RequestInfo(BaseModel):
    message: str = Field(min_length=10, max_length=2000)


class Escalate(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    kind: str  # AIPrediction.kind used when the step is proposed / recorded
    risk: Risk
    input_model: type[BaseModel]
    description: str
    validate: Callable[[ToolContext, BaseModel], str | None]
    verify: Callable[[ToolContext, BaseModel], bool] | None = None


def _v_category(ctx: ToolContext, a: BaseModel) -> str | None:
    assert isinstance(a, SetCategory)
    names = {c.name for c in ticket_svc.org_categories(ctx.db, ctx.tenant.id)}
    if a.category not in names:
        return f"unknown category {a.category!r}"
    return "already set" if ctx.ticket.category == a.category else None


def _v_priority(ctx: ToolContext, a: BaseModel) -> str | None:
    assert isinstance(a, SetPriority)
    return "already set" if ctx.ticket.priority == a.priority else None


def _v_team(ctx: ToolContext, a: BaseModel) -> str | None:
    assert isinstance(a, RouteTeam)
    team = ctx.db.get(Team, a.team_id)
    if team is None or team.tenant_id != ctx.tenant.id:
        return "team is not in this organization"
    return "already routed there" if ctx.ticket.team_id == a.team_id else None


def _v_assign(ctx: ToolContext, a: BaseModel) -> str | None:
    assert isinstance(a, AssignAgent)
    user = ctx.db.get(User, a.user_id)
    if user is None or user.tenant_id != ctx.tenant.id or not user.is_active or user.role not in ASSIGNABLE_ROLES:
        return "assignee is not an active agent of this organization"
    return "already assigned" if ctx.ticket.assigned_to_user_id == a.user_id else None


def _v_duplicate(ctx: ToolContext, a: BaseModel) -> str | None:
    assert isinstance(a, LinkDuplicate)
    other = ctx.db.get(Ticket, a.ticket_id)
    if other is None or other.tenant_id != ctx.tenant.id or other.id == ctx.ticket.id:
        return "not a ticket of this organization"
    return None


def _open(ctx: ToolContext, _a: BaseModel) -> str | None:
    return "ticket is closed" if ctx.ticket.status in ("resolved", "closed") else None


def _v_request_info(ctx: ToolContext, a: BaseModel) -> str | None:
    if ctx.ticket.status in ("resolved", "closed", "waiting_for_customer"):
        return f"cannot ask the requester while the ticket is {ctx.ticket.status}"
    return None


def _v_escalate(ctx: ToolContext, a: BaseModel) -> str | None:
    try:
        ticket_svc.check_transition(ctx.ticket, TicketStatus.ESCALATED, None, "system")
    except ticket_svc.TicketError as e:
        return e.message
    return None


def _field_equals(attr: str, arg: str) -> Callable[[ToolContext, BaseModel], bool]:
    def verify(ctx: ToolContext, a: BaseModel) -> bool:
        ctx.db.refresh(ctx.ticket)
        return getattr(ctx.ticket, attr) == getattr(a, arg)

    return verify


TOOLS: dict[str, ToolSpec] = {
    t.name: t
    for t in (
        ToolSpec(
            "set_category",
            "category",
            "low",
            SetCategory,
            "Set the ticket's category",
            _v_category,
            _field_equals("category", "category"),
        ),
        ToolSpec(
            "set_priority",
            "priority",
            "medium",
            SetPriority,
            "Set the ticket's priority (changes SLA targets)",
            _v_priority,
            _field_equals("priority", "priority"),
        ),
        ToolSpec(
            "route_to_team",
            "team",
            "medium",
            RouteTeam,
            "Route the ticket to a team",
            _v_team,
            _field_equals("team_id", "team_id"),
        ),
        ToolSpec(
            "assign",
            "assignee",
            "medium",
            AssignAgent,
            "Assign the ticket to an agent",
            _v_assign,
            _field_equals("assigned_to_user_id", "user_id"),
        ),
        ToolSpec(
            "link_duplicate", "duplicate", "high", LinkDuplicate, "Mark as a duplicate of another ticket", _v_duplicate
        ),
        ToolSpec("send_reply", "reply", "high", SendReply, "Send a public reply to the requester", _open),
        ToolSpec(
            "request_info",
            "request_info",
            "high",
            RequestInfo,
            "Ask the requester for missing details and pause the SLA clock",
            _v_request_info,
        ),
        ToolSpec("escalate", "escalate", "high", Escalate, "Escalate the ticket to managers", _v_escalate),
    )
}
KIND_TO_TOOL = {t.kind: t for t in TOOLS.values()}
