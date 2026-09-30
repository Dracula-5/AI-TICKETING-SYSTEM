"""
Ticket lifecycle: the single place that knows which status changes are legal,
who may make them, and what each one does to SLA clocks, timestamps,
notifications, status history and the audit log.

    submitted → triaged → assigned → acknowledged → in_progress ⇄ waiting_for_customer
         ↘ escalated (from any open state; needs a reason)
    … → resolved → closed (requester confirms · manager · auto-close)
    resolved/closed → reopened (needs a reason)

"Created" is the creation event itself: the first status_history row has
from_status = NULL, to_status = submitted.

Nothing here commits; callers commit once so the change, its history row, its
audit entry and its notifications land atomically.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai.rules import PRIORITIES, classify_category, classify_priority
from app.core.config import settings
from app.core.rbac import ASSIGNABLE_ROLES, P, Role, can_read_all_tickets, has_permission, is_staff
from app.db.database import utcnow
from app.db.models import (
    Category,
    SlaPolicy,
    Team,
    TeamMember,
    Tenant,
    Ticket,
    TicketComment,
    TicketStatusHistory,
    User,
)
from app.services import audit, jobs
from app.services.notification_service import notify, notify_many
from app.services.organizations import org_setting


class TicketStatus(StrEnum):
    SUBMITTED = "submitted"
    TRIAGED = "triaged"
    ASSIGNED = "assigned"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    WAITING_FOR_CUSTOMER = "waiting_for_customer"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REOPENED = "reopened"


S = TicketStatus
TERMINAL_STATUSES = frozenset({S.RESOLVED, S.CLOSED})
OPEN_STATUSES = frozenset(set(S) - TERMINAL_STATUSES)
# Statuses in which an assignee is expected to be working the ticket.
WORKING_STATUSES = frozenset({S.ASSIGNED, S.ACKNOWLEDGED, S.IN_PROGRESS, S.WAITING_FOR_CUSTOMER, S.ESCALATED})


class TicketError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Transition policy
# ---------------------------------------------------------------------------
# Actor kinds a rule can allow:
#   requester · assignee · staff (TICKETS_WORK) · manager (TICKETS_CLOSE_ANY) · system
@dataclass(frozen=True)
class Rule:
    sources: frozenset
    actors: frozenset
    needs_reason: bool = False


_ALL_OPEN_BUT = lambda *excluded: frozenset(OPEN_STATUSES - set(excluded))  # noqa: E731

TRANSITIONS: dict[TicketStatus, Rule] = {
    S.TRIAGED: Rule(frozenset({S.SUBMITTED, S.REOPENED}), frozenset({"staff", "system"})),
    # Entered through assign(), never via the generic transition endpoint.
    S.ASSIGNED: Rule(frozenset(), frozenset()),
    S.ACKNOWLEDGED: Rule(frozenset({S.ASSIGNED}), frozenset({"assignee", "manager"})),
    S.IN_PROGRESS: Rule(
        frozenset({S.ASSIGNED, S.ACKNOWLEDGED, S.WAITING_FOR_CUSTOMER, S.ESCALATED, S.REOPENED}),
        frozenset({"assignee", "manager", "system"}),
    ),
    S.WAITING_FOR_CUSTOMER: Rule(
        frozenset({S.ASSIGNED, S.ACKNOWLEDGED, S.IN_PROGRESS, S.ESCALATED}),
        frozenset({"assignee", "manager"}),
        needs_reason=True,
    ),
    S.ESCALATED: Rule(_ALL_OPEN_BUT(S.ESCALATED), frozenset({"staff", "system"}), needs_reason=True),
    S.RESOLVED: Rule(
        frozenset({S.ASSIGNED, S.ACKNOWLEDGED, S.IN_PROGRESS, S.WAITING_FOR_CUSTOMER, S.ESCALATED, S.REOPENED}),
        frozenset({"assignee", "manager"}),
    ),
    S.CLOSED: Rule(frozenset(set(S) - {S.CLOSED}), frozenset({"requester", "manager", "system"}), needs_reason=True),
    S.REOPENED: Rule(frozenset({S.RESOLVED, S.CLOSED}), frozenset({"requester", "staff"}), needs_reason=True),
}

# Requesters may close their own ticket only to confirm a resolution or to
# withdraw it before anyone has started work.
_REQUESTER_CLOSE_SOURCES = frozenset({S.RESOLVED, S.SUBMITTED, S.TRIAGED, S.ASSIGNED})


def _actor_kinds(ticket: Ticket, user: User | None, actor_type: str) -> set[str]:
    if user is None:
        return {"system"} if actor_type in ("system", "ai") else set()
    kinds = set()
    if ticket.created_by_user_id == user.id:
        kinds.add("requester")
    if has_permission(user.role, P.TICKETS_WORK):
        kinds.add("staff")
        if ticket.assigned_to_user_id == user.id:
            kinds.add("assignee")
    if has_permission(user.role, P.TICKETS_CLOSE_ANY):
        kinds.add("manager")
    return kinds


def check_transition(ticket: Ticket, to_status: TicketStatus, user: User | None, actor_type: str = "user") -> Rule:
    rule = TRANSITIONS.get(to_status)
    current = TicketStatus(ticket.status)
    if rule is None or not rule.sources:
        raise TicketError(f"Tickets cannot be moved to '{to_status}' directly")
    if current not in rule.sources:
        raise TicketError(f"Cannot move a ticket from '{current}' to '{to_status}'", 409)
    kinds = _actor_kinds(ticket, user, actor_type)
    allowed = kinds & rule.actors
    if not allowed:
        raise TicketError("You are not allowed to make this status change", 403)
    if to_status == S.CLOSED and allowed == {"requester"} and current not in _REQUESTER_CLOSE_SOURCES:
        raise TicketError("This ticket is being worked on; ask the assignee to resolve it", 403)
    if (
        to_status in (S.IN_PROGRESS, S.ACKNOWLEDGED, S.WAITING_FOR_CUSTOMER, S.RESOLVED)
        and ticket.assigned_to_user_id is None
    ):
        raise TicketError("Assign the ticket before working on it", 409)
    if to_status == S.REOPENED and current == S.CLOSED and ticket.closed_at is not None:
        window = int(org_setting(ticket.tenant, "reopen_window_days"))
        if utcnow() - ticket.closed_at > timedelta(days=window):
            raise TicketError(f"Closed tickets can only be reopened within {window} days; open a new ticket", 409)
    return rule


def allowed_transitions(ticket: Ticket, user: User) -> list[str]:
    result = []
    for status in TRANSITIONS:
        try:
            check_transition(ticket, status, user)
            result.append(status.value)
        except TicketError:
            continue
    return result


# ---------------------------------------------------------------------------
# SLA clocks
# ---------------------------------------------------------------------------
def _policy(db: Session, tenant_id: int, priority: str) -> SlaPolicy | None:
    return db.query(SlaPolicy).filter(SlaPolicy.tenant_id == tenant_id, SlaPolicy.priority == priority).first()


def apply_sla_policy(db: Session, ticket: Ticket) -> None:
    """(Re)compute due dates from creation time and the org's policy for the
    ticket's priority. Breach timestamps already recorded are never cleared,
    so lowering the priority cannot erase a breach."""
    policy = _policy(db, ticket.tenant_id, ticket.priority)
    if policy is None:
        ticket.first_response_due = ticket.resolution_due = None
        return
    created = ticket.created_at or utcnow()
    ticket.first_response_due = created + timedelta(minutes=policy.first_response_minutes)
    ticket.resolution_due = created + timedelta(minutes=policy.resolution_minutes)


def _mark_first_response(ticket: Ticket, now: datetime) -> None:
    if ticket.first_responded_at is None:
        ticket.first_responded_at = now


def _resume_sla_clock(ticket: Ticket, now: datetime) -> None:
    if ticket.sla_paused_at is not None:
        if ticket.resolution_due is not None and ticket.resolution_breached_at is None:
            ticket.resolution_due += now - ticket.sla_paused_at
        ticket.sla_paused_at = None


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------
def staff_lead_ids(db: Session, tenant_id: int) -> list[int]:
    return [
        uid
        for (uid,) in db.query(User.id).filter(
            User.tenant_id == tenant_id,
            User.is_active.is_(True),
            User.role.in_([Role.MANAGER.value, Role.ORG_ADMIN.value]),
        )
    ]


def _link(ticket: Ticket) -> str:
    return f"/tickets/{ticket.id}"


def transition(
    db: Session,
    ticket: Ticket,
    to_status: TicketStatus | str,
    *,
    actor: User | None,
    actor_type: str = "user",
    reason: str | None = None,
    resolution_summary: str | None = None,
    enforce: bool = True,
) -> TicketStatusHistory:
    to_status = TicketStatus(to_status)
    reason = (reason or "").strip() or None
    if enforce:
        rule = check_transition(ticket, to_status, actor, actor_type)
        if rule.needs_reason and not reason:
            raise TicketError(f"A reason is required to move a ticket to '{to_status}'", 422)
        if to_status == S.RESOLVED and not (resolution_summary or "").strip():
            raise TicketError("A resolution summary is required to resolve a ticket", 422)

    now = utcnow()
    from_status = TicketStatus(ticket.status) if ticket.status else None

    if from_status == S.WAITING_FOR_CUSTOMER and to_status != S.WAITING_FOR_CUSTOMER:
        _resume_sla_clock(ticket, now)

    if to_status == S.ACKNOWLEDGED:
        ticket.acknowledged_at = now
        _mark_first_response(ticket, now)
    elif to_status == S.IN_PROGRESS:
        if ticket.acknowledged_at is None:
            ticket.acknowledged_at = now
        _mark_first_response(ticket, now)
    elif to_status == S.WAITING_FOR_CUSTOMER:
        ticket.sla_paused_at = now
        if ticket.acknowledged_at is None:
            ticket.acknowledged_at = now
        _mark_first_response(ticket, now)
        if actor is not None and reason:
            # The reason is the question for the requester: keep it in the
            # conversation, not only in the status history.
            db.add(
                TicketComment(
                    tenant_id=ticket.tenant_id,
                    ticket_id=ticket.id,
                    author_user_id=actor.id,
                    visibility="public",
                    content=reason,
                    created_at=now,
                )
            )
    elif to_status == S.RESOLVED:
        ticket.resolved_at = now
        ticket.resolution_summary = resolution_summary.strip() if resolution_summary else ticket.resolution_summary
        _mark_first_response(ticket, now)
    elif to_status == S.CLOSED:
        ticket.closed_at = now
    elif to_status == S.REOPENED:
        ticket.reopened_count = (ticket.reopened_count or 0) + 1
        ticket.resolved_at = None
        ticket.closed_at = None

    ticket.status = to_status.value
    ticket.updated_at = now
    entry = TicketStatusHistory(
        tenant_id=ticket.tenant_id,
        ticket_id=ticket.id,
        from_status=from_status.value if from_status else None,
        to_status=to_status.value,
        actor_user_id=actor.id if actor else None,
        actor_type=actor_type if actor is None else "user",
        reason=reason,
        created_at=now,
    )
    db.add(entry)
    audit.record(
        db,
        "ticket.transition",
        tenant_id=ticket.tenant_id,
        actor=actor,
        actor_type=None if actor else actor_type,
        entity_type="ticket",
        entity_id=ticket.id,
        changes={"status": [entry.from_status, entry.to_status], **({"reason": reason} if reason else {})},
    )
    _notify_transition(db, ticket, to_status, actor, reason)
    return entry


def _notify_transition(
    db: Session, ticket: Ticket, to_status: TicketStatus, actor: User | None, reason: str | None
) -> None:
    actor_id = actor.id if actor else None
    label = f"#{ticket.number} {ticket.title}"
    if to_status == S.RESOLVED and ticket.created_by_user_id != actor_id:
        notify(
            db,
            ticket.tenant_id,
            ticket.created_by_user_id,
            type_="ticket_resolved",
            title=f"Resolved: {label}",
            message="Please confirm the resolution or reopen the ticket.",
            link=_link(ticket),
        )
    elif to_status == S.WAITING_FOR_CUSTOMER and ticket.created_by_user_id != actor_id:
        notify(
            db,
            ticket.tenant_id,
            ticket.created_by_user_id,
            type_="ticket_waiting",
            title=f"Your input is needed: {label}",
            message=reason,
            link=_link(ticket),
        )
    elif to_status == S.ESCALATED:
        recipients = set(staff_lead_ids(db, ticket.tenant_id)) | {ticket.assigned_to_user_id}
        notify_many(
            db,
            ticket.tenant_id,
            recipients - {actor_id},
            type_="ticket_escalated",
            title=f"Escalated: {label}",
            message=reason,
            link=_link(ticket),
        )
    elif to_status == S.REOPENED and ticket.assigned_to_user_id and ticket.assigned_to_user_id != actor_id:
        notify(
            db,
            ticket.tenant_id,
            ticket.assigned_to_user_id,
            type_="ticket_reopened",
            title=f"Reopened: {label}",
            message=reason,
            link=_link(ticket),
        )


# ---------------------------------------------------------------------------
# Creation, triage and assignment
# ---------------------------------------------------------------------------
def next_ticket_number(db: Session, tenant_id: int) -> int:
    # The UPDATE row-locks the tenant until commit, so concurrent creations in
    # one org serialize here and numbers never collide.
    db.query(Tenant).filter(Tenant.id == tenant_id).update(
        {Tenant.ticket_seq: Tenant.ticket_seq + 1}, synchronize_session=False
    )
    return db.query(Tenant.ticket_seq).filter(Tenant.id == tenant_id).scalar()


def org_categories(db: Session, tenant_id: int) -> list[Category]:
    return (
        db.query(Category)
        .filter(Category.tenant_id == tenant_id, Category.is_active.is_(True))
        .order_by(Category.id)
        .all()
    )


def create_ticket(
    db: Session,
    *,
    requester: User,
    title: str,
    description: str,
    priority: str | None = None,
    category: str | None = None,
    channel: str = "web",
    data_origin: str = "real",
    created_at: datetime | None = None,
    analyze: bool = True,
) -> Ticket:
    if requester.tenant_id is None:
        raise TicketError("Only organization members can create tickets", 403)
    now = created_at or utcnow()
    ticket = Ticket(
        tenant_id=requester.tenant_id,
        number=next_ticket_number(db, requester.tenant_id),
        title=title.strip(),
        description=description.strip(),
        priority=priority or "medium",
        category=category,
        status=S.SUBMITTED.value,
        channel=channel,
        created_by_user_id=requester.id,
        data_origin=data_origin,
        created_at=now,
        updated_at=now,
    )
    db.add(ticket)
    db.flush()
    db.add(
        TicketStatusHistory(
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            from_status=None,
            to_status=S.SUBMITTED.value,
            actor_user_id=requester.id,
            actor_type="user",
            reason=f"Created via {channel}",
            created_at=now,
        )
    )
    audit.record(
        db,
        "ticket.create",
        tenant_id=ticket.tenant_id,
        actor=requester,
        entity_type="ticket",
        entity_id=ticket.id,
        changes={"number": ticket.number, "channel": channel},
    )
    triage_with_rules(db, ticket, requested_priority=priority, requested_category=category)
    apply_sla_policy(db, ticket)
    if settings.ai_enabled and analyze:
        # AI triage runs in the background worker; enqueued in this transaction
        # so it exists exactly when the ticket does.
        jobs.enqueue(
            db, "ai.triage", {"ticket_id": ticket.id}, tenant_id=ticket.tenant_id, dedupe_key=f"ai.triage:{ticket.id}"
        )
    return ticket


def triage_with_rules(
    db: Session, ticket: Ticket, *, requested_priority: str | None, requested_category: str | None
) -> None:
    """Baseline triage: fill in whatever the requester didn't specify using the
    deterministic rules, route to the category's default team, optionally
    auto-assign, and record the reasoning in the status history."""
    text = f"{ticket.title}\n{ticket.description}"
    categories = org_categories(db, ticket.tenant_id)
    explanations = []

    if requested_category:
        ticket.category = requested_category
        explanations.append(f"category={requested_category} (chosen by requester)")
    else:
        decision = classify_category(text, [(c.name, c.keywords) for c in categories])
        ticket.category = decision.value
        explanations.append(decision.explain("category"))

    if requested_priority:
        explanations.append(f"priority={requested_priority} (chosen by requester)")
    else:
        decision = classify_priority(text)
        ticket.priority = decision.value or "low"
        explanations.append(decision.explain("priority"))

    category = next((c for c in categories if c.name == ticket.category), None)
    if category and category.default_team_id:
        ticket.team_id = category.default_team_id
        team_name = category.default_team.name if category.default_team else category.default_team_id
        explanations.append(f"team={team_name} (routing rule for {category.name})")

    ticket.triage_source = "rules"
    transition(
        db,
        ticket,
        S.TRIAGED,
        actor=None,
        actor_type="system",
        reason="Rules engine: " + "; ".join(explanations),
        enforce=False,
    )

    if ticket.team_id and org_setting(ticket.tenant, "auto_assign"):
        agent_id = least_loaded_agent(db, ticket.tenant_id, ticket.team_id)
        if agent_id:
            assign(
                db,
                ticket,
                assignee_id=agent_id,
                team_id=ticket.team_id,
                actor=None,
                actor_type="system",
                reason="Auto-assigned to the team member with the fewest open tickets",
            )


def least_loaded_agent(db: Session, tenant_id: int, team_id: int) -> int | None:
    open_count = func.count(Ticket.id).filter(Ticket.status.in_([s.value for s in OPEN_STATUSES]))
    row = (
        db.query(User.id, open_count.label("open"))
        .join(TeamMember, TeamMember.user_id == User.id)
        .outerjoin(Ticket, (Ticket.assigned_to_user_id == User.id) & (Ticket.tenant_id == tenant_id))
        .filter(
            TeamMember.team_id == team_id,
            User.tenant_id == tenant_id,
            User.is_active.is_(True),
            User.role == Role.AGENT.value,
        )
        .group_by(User.id)
        .order_by(open_count.asc(), User.id.asc())
        .first()
    )
    return row[0] if row else None


def assign(
    db: Session,
    ticket: Ticket,
    *,
    assignee_id: int | None,
    team_id: int | None = None,
    actor: User | None,
    actor_type: str = "user",
    reason: str | None = None,
) -> None:
    if TicketStatus(ticket.status) in TERMINAL_STATUSES:
        raise TicketError("Resolved or closed tickets cannot be reassigned; reopen the ticket first", 409)

    if team_id is not None:
        team = db.query(Team).filter(Team.id == team_id, Team.tenant_id == ticket.tenant_id).first()
        if team is None:
            raise TicketError("Team not found", 404)

    assignee = None
    if assignee_id is not None:
        assignee = db.query(User).filter(User.id == assignee_id, User.tenant_id == ticket.tenant_id).first()
        if assignee is None or not assignee.is_active:
            raise TicketError("Assignee not found in this organization", 404)
        if assignee.role not in ASSIGNABLE_ROLES:
            raise TicketError("Tickets can only be assigned to agents, managers or admins", 422)

    before = {"assigned_to_user_id": ticket.assigned_to_user_id, "team_id": ticket.team_id}
    if team_id is not None:
        ticket.team_id = team_id
    ticket.assigned_to_user_id = assignee.id if assignee else None
    after = {"assigned_to_user_id": ticket.assigned_to_user_id, "team_id": ticket.team_id}
    changes = audit.diff(before, after)
    if not changes:
        return

    current = TicketStatus(ticket.status)
    new_status = None
    if assignee and before["assigned_to_user_id"] != assignee.id and current != S.WAITING_FOR_CUSTOMER:
        new_status = S.ASSIGNED
    elif assignee is None and current in WORKING_STATUSES - {S.WAITING_FOR_CUSTOMER, S.ESCALATED}:
        new_status = S.TRIAGED

    audit.record(
        db,
        "ticket.assign",
        tenant_id=ticket.tenant_id,
        actor=actor,
        actor_type=None if actor else actor_type,
        entity_type="ticket",
        entity_id=ticket.id,
        changes=changes,
    )
    if new_status and new_status != current:
        who = assignee.name if assignee else "nobody"
        transition(
            db,
            ticket,
            new_status,
            actor=actor,
            actor_type=actor_type,
            reason=reason or f"Assigned to {who}",
            enforce=False,
        )
    ticket.updated_at = utcnow()

    if assignee and (actor is None or assignee.id != actor.id):
        notify(
            db,
            ticket.tenant_id,
            assignee.id,
            type_="ticket_assigned",
            title=f"Assigned to you: #{ticket.number} {ticket.title}",
            message=f"Priority {ticket.priority} · {ticket.category or 'uncategorized'}",
            link=_link(ticket),
        )


def _team_in_org(db: Session, team_id: int, tenant_id: int) -> bool:
    return db.query(Team.id).filter(Team.id == team_id, Team.tenant_id == tenant_id).first() is not None


def update_fields(db: Session, ticket: Ticket, *, actor: User, fields: dict) -> dict:
    """Staff edits of priority/category/team/title/description."""
    before = {k: getattr(ticket, k) for k in fields}
    if "category" in fields and fields["category"] is not None:
        names = {c.name for c in org_categories(db, ticket.tenant_id)}
        if fields["category"] not in names:
            raise TicketError("Unknown category for this organization", 422)
    if "priority" in fields and fields["priority"] not in PRIORITIES:
        raise TicketError("Invalid priority", 422)
    team_id = fields.get("team_id")
    if team_id is not None and not _team_in_org(db, team_id, ticket.tenant_id):
        raise TicketError("Team not found", 404)

    for key, value in fields.items():
        setattr(ticket, key, value)
    changes = audit.diff(before, fields)
    if not changes:
        return {}
    if "priority" in changes:
        apply_sla_policy(db, ticket)
    if {"priority", "category", "team_id"} & changes.keys():
        ticket.triage_source = "manual"
    ticket.updated_at = utcnow()
    audit.record(
        db,
        "ticket.update",
        tenant_id=ticket.tenant_id,
        actor=actor,
        entity_type="ticket",
        entity_id=ticket.id,
        changes=changes,
    )
    return changes


# ---------------------------------------------------------------------------
# Visibility
# ---------------------------------------------------------------------------
def visible_tickets_query(db: Session, user: User):
    """Every ticket read goes through this: tenant filter always, plus
    requester filter for roles that may only see their own tickets."""
    q = db.query(Ticket).filter(Ticket.tenant_id == user.tenant_id)
    if not can_read_all_tickets(user.role):
        q = q.filter(Ticket.created_by_user_id == user.id)
    return q


def get_visible_ticket(db: Session, ticket_id: int, user: User) -> Ticket:
    ticket = visible_tickets_query(db, user).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        # 404 rather than 403, so ticket ids in other orgs are not confirmed to exist.
        raise TicketError("Ticket not found", 404)
    return ticket


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------
_MENTION = re.compile(r"@([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")


def add_comment(db: Session, ticket: Ticket, *, author: User, content: str, visibility: str) -> TicketComment:
    if visibility not in ("public", "internal"):
        raise TicketError("visibility must be 'public' or 'internal'", 422)
    if visibility == "internal" and not has_permission(author.role, P.COMMENTS_INTERNAL):
        raise TicketError("Only support staff can add internal notes", 403)
    staff = is_staff(author.role)
    if not staff and ticket.created_by_user_id != author.id:
        raise TicketError("Only the requester or support staff can comment on this ticket", 403)
    if TicketStatus(ticket.status) == S.CLOSED and not staff:
        raise TicketError("This ticket is closed; reopen it to add a reply", 409)

    now = utcnow()
    comment = TicketComment(
        tenant_id=ticket.tenant_id,
        ticket_id=ticket.id,
        author_user_id=author.id,
        visibility=visibility,
        content=content.strip(),
        created_at=now,
    )
    db.add(comment)
    db.flush()
    audit.record(
        db,
        "comment.create",
        tenant_id=ticket.tenant_id,
        actor=author,
        entity_type="comment",
        entity_id=comment.id,
        changes={"ticket_id": ticket.id, "visibility": visibility},
    )

    if staff and visibility == "public" and ticket.created_by_user_id != author.id:
        _mark_first_response(ticket, now)
    ticket.updated_at = now

    # A requester's reply restarts work on a ticket that was waiting on them.
    if ticket.created_by_user_id == author.id and ticket.status == S.WAITING_FOR_CUSTOMER.value:
        transition(
            db, ticket, S.IN_PROGRESS, actor=None, actor_type="system", reason="Requester replied", enforce=False
        )

    _notify_comment(db, ticket, comment, author)
    return comment


def _notify_comment(db: Session, ticket: Ticket, comment: TicketComment, author: User) -> None:
    label = f"#{ticket.number} {ticket.title}"
    recipients: set[int] = set()
    if comment.visibility == "public":
        if author.id != ticket.created_by_user_id:
            recipients.add(ticket.created_by_user_id)
        elif ticket.assigned_to_user_id:
            recipients.add(ticket.assigned_to_user_id)
    elif ticket.assigned_to_user_id and ticket.assigned_to_user_id != author.id:
        recipients.add(ticket.assigned_to_user_id)
    notify_many(
        db,
        ticket.tenant_id,
        recipients - {author.id},
        type_="ticket_comment",
        title=f"New {'reply' if comment.visibility == 'public' else 'internal note'} on {label}",
        message=f"{author.name}: {comment.content[:140]}",
        link=_link(ticket),
    )

    mentioned = {m.lower() for m in _MENTION.findall(comment.content)}
    if mentioned:
        users = db.query(User).filter(User.tenant_id == ticket.tenant_id, func.lower(User.email).in_(mentioned)).all()
        # Only notify people who can actually open the ticket; internal notes
        # never reach non-staff.
        allowed = [
            u.id
            for u in users
            if u.id != author.id
            and u.is_active
            and (is_staff(u.role) or (comment.visibility == "public" and u.id == ticket.created_by_user_id))
        ]
        notify_many(
            db,
            ticket.tenant_id,
            set(allowed) - recipients,
            type_="mention",
            title=f"{author.name} mentioned you on {label}",
            message=comment.content[:140],
            link=_link(ticket),
        )


def visible_comments_query(db: Session, ticket: Ticket, user: User):
    q = db.query(TicketComment).filter(
        TicketComment.ticket_id == ticket.id, TicketComment.tenant_id == ticket.tenant_id
    )
    if not has_permission(user.role, P.COMMENTS_INTERNAL) and user.role != Role.ANALYST.value:
        q = q.filter(TicketComment.visibility == "public")
    return q.order_by(TicketComment.created_at.asc(), TicketComment.id.asc())
