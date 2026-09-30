from datetime import datetime
from typing import NoReturn

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import ColumnElement, case, func, or_
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.deps import get_org_user, org_id, require_permission
from app.core.limiter import limiter
from app.core.rbac import P, has_permission, is_staff
from app.db.database import get_db, utcnow
from app.db.models import Attachment, Ticket, TicketComment, TicketStatusHistory, User
from app.schemas.common import Page
from app.schemas.tickets import (
    AssignIn,
    AttachmentOut,
    CommentCreate,
    CommentOut,
    ConfirmResolutionIn,
    SlaState,
    StatusHistoryOut,
    TicketCreate,
    TicketDetailOut,
    TicketOut,
    TicketUpdate,
    TransitionIn,
)
from app.services import audit
from app.services import tickets as svc
from app.services.sla import AT_RISK_FRACTION, at_risk_clause
from app.services.storage import UploadRejected, get_storage, sha256, validate_upload
from app.services.tickets import OPEN_STATUSES, TERMINAL_STATUSES, TicketError, TicketStatus

router = APIRouter(prefix="/tickets", tags=["tickets"])

_PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _raise(err: TicketError) -> NoReturn:
    raise HTTPException(status_code=err.status_code, detail=err.message)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------
def sla_state(t: Ticket, now: datetime) -> SlaState:
    breached = bool(t.first_response_breached_at or t.resolution_breached_at)
    if t.status in (TicketStatus.RESOLVED.value, TicketStatus.CLOSED.value):
        state = "breached" if breached else ("met" if t.resolution_due else "none")
    elif t.sla_paused_at is not None:
        state = "paused"
    elif breached:
        state = "breached"
    elif t.resolution_due is None:
        state = "none"
    else:
        state = "ok"
        windows = [(t.created_at, t.resolution_due)]
        if t.first_responded_at is None and t.first_response_due is not None:
            windows.append((t.created_at, t.first_response_due))
        for start, due in windows:
            if due - now <= (due - start) * AT_RISK_FRACTION:
                state = "at_risk"
    return SlaState(
        first_response_due=t.first_response_due,
        first_responded_at=t.first_responded_at,
        first_response_breached=t.first_response_breached_at is not None,
        resolution_due=t.resolution_due,
        resolution_breached=t.resolution_breached_at is not None,
        paused=t.sla_paused_at is not None,
        state=state,
    )


def ticket_out(t: Ticket, now: datetime | None = None) -> TicketOut:
    now = now or utcnow()
    return TicketOut.model_validate(
        {
            **{
                c: getattr(t, c)
                for c in (
                    "id",
                    "number",
                    "title",
                    "description",
                    "priority",
                    "category",
                    "status",
                    "channel",
                    "triage_source",
                    "acknowledged_at",
                    "resolved_at",
                    "closed_at",
                    "reopened_count",
                    "resolution_summary",
                    "data_origin",
                    "created_at",
                    "updated_at",
                )
            },
            "requester": t.requester,
            "assignee": t.assignee,
            "team": t.team,
            "sla": sla_state(t, now),
        }
    )


def _can_assign(ticket: Ticket, user: User) -> bool:
    if ticket.status in (TicketStatus.RESOLVED.value, TicketStatus.CLOSED.value):
        return False
    if has_permission(user.role, P.TICKETS_ASSIGN):
        return True
    return has_permission(user.role, P.TICKETS_WORK) and ticket.assigned_to_user_id in (None, user.id)


def _can_edit(ticket: Ticket, user: User) -> bool:
    if has_permission(user.role, P.TICKETS_WORK):
        return ticket.status != TicketStatus.CLOSED.value
    return ticket.created_by_user_id == user.id and ticket.status in (
        TicketStatus.SUBMITTED.value,
        TicketStatus.TRIAGED.value,
    )


def detail_out(ticket: Ticket, user: User) -> TicketDetailOut:
    return TicketDetailOut.model_validate(
        {
            **ticket_out(ticket).model_dump(),
            "allowed_transitions": svc.allowed_transitions(ticket, user),
            "can_assign": _can_assign(ticket, user),
            "can_edit": _can_edit(ticket, user),
        }
    )


def _load(db: Session, ticket_id: int, user: User) -> Ticket:
    try:
        return svc.get_visible_ticket(db, ticket_id, user)
    except TicketError as e:
        _raise(e)


# ---------------------------------------------------------------------------
# Create / list / read / update
# ---------------------------------------------------------------------------
@router.post("", response_model=TicketDetailOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_ticket(
    request: Request,
    payload: TicketCreate,
    user: User = Depends(require_permission(P.TICKETS_CREATE)),
    db: Session = Depends(get_db),
):
    if payload.category is not None and payload.category not in {c.name for c in svc.org_categories(db, org_id(user))}:
        raise HTTPException(status_code=422, detail="Unknown category for this organization")
    try:
        ticket = svc.create_ticket(
            db,
            requester=user,
            title=payload.title,
            description=payload.description,
            priority=payload.priority,
            category=payload.category,
        )
    except TicketError as e:
        _raise(e)
    db.commit()
    db.refresh(ticket)
    return detail_out(ticket, user)


@router.get("", response_model=Page[TicketOut])
def list_tickets(
    status_: str | None = Query(
        default=None, alias="status", description="Comma-separated statuses, or 'open' / 'done'"
    ),
    priority: str | None = None,
    category: str | None = None,
    team_id: int | None = None,
    assignee: str | None = Query(default=None, description="'me', 'unassigned' or a user id"),
    requester: str | None = Query(default=None, description="'me' or a user id"),
    sla: str | None = Query(default=None, pattern="^(breached|at_risk)$"),
    q: str | None = Query(default=None, max_length=200),
    sort: str = Query(default="-created_at", pattern="^-?(created_at|updated_at|priority|resolution_due|number)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    user: User = Depends(get_org_user),
    db: Session = Depends(get_db),
):
    query = svc.visible_tickets_query(db, user)
    now = utcnow()

    if status_:
        if status_ == "open":
            query = query.filter(Ticket.status.in_([s.value for s in OPEN_STATUSES]))
        elif status_ == "done":
            query = query.filter(Ticket.status.in_([s.value for s in TERMINAL_STATUSES]))
        else:
            query = query.filter(Ticket.status.in_(status_.split(",")))
    if priority:
        query = query.filter(Ticket.priority.in_(priority.split(",")))
    if category:
        query = query.filter(Ticket.category == category)
    if team_id is not None:
        query = query.filter(Ticket.team_id == team_id)
    if assignee == "me":
        query = query.filter(Ticket.assigned_to_user_id == user.id)
    elif assignee == "unassigned":
        query = query.filter(Ticket.assigned_to_user_id.is_(None))
    elif assignee:
        query = query.filter(Ticket.assigned_to_user_id == _int(assignee, "assignee"))
    if requester == "me":
        query = query.filter(Ticket.created_by_user_id == user.id)
    elif requester:
        query = query.filter(Ticket.created_by_user_id == _int(requester, "requester"))
    if sla:
        query = query.filter(Ticket.status.in_([s.value for s in OPEN_STATUSES]))
        if sla == "breached":
            query = query.filter(
                or_(Ticket.first_response_breached_at.isnot(None), Ticket.resolution_breached_at.isnot(None))
            )
        else:
            query = query.filter(at_risk_clause(db, org_id(user), now))
    if q:
        like = f"%{q.lower()}%"
        conditions: list[ColumnElement[bool]] = [
            func.lower(Ticket.title).like(like),
            func.lower(Ticket.description).like(like),
        ]
        if q.lstrip("#").isdigit():
            conditions.append(Ticket.number == int(q.lstrip("#")))
        query = query.filter(or_(*conditions))

    total = query.count()
    desc = sort.startswith("-")
    key = sort.lstrip("-")
    if key == "priority":
        column = case(_PRIORITY_RANK, value=Ticket.priority, else_=9)
        desc = not desc  # "-priority" = most urgent first
    else:
        column = getattr(Ticket, key)
    order = column.desc() if desc else column.asc()
    items = (
        query.options(joinedload(Ticket.requester), joinedload(Ticket.assignee), joinedload(Ticket.team))
        .order_by(order, Ticket.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return Page(items=[ticket_out(t, now) for t in items], total=total, page=page, page_size=page_size)


def _int(value: str, name: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{name} must be 'me', 'unassigned' or a number") from None


@router.get("/{ticket_id}", response_model=TicketDetailOut)
def get_ticket(ticket_id: int, user: User = Depends(get_org_user), db: Session = Depends(get_db)):
    return detail_out(_load(db, ticket_id, user), user)


@router.patch("/{ticket_id}", response_model=TicketDetailOut)
def update_ticket(
    ticket_id: int, payload: TicketUpdate, user: User = Depends(get_org_user), db: Session = Depends(get_db)
):
    ticket = _load(db, ticket_id, user)
    fields = payload.model_dump(exclude_unset=True)
    if not _can_edit(ticket, user):
        raise HTTPException(status_code=403, detail="You cannot edit this ticket")
    if not has_permission(user.role, P.TICKETS_WORK) and set(fields) - {"title", "description"}:
        raise HTTPException(status_code=403, detail="Only support staff can change priority, category or team")
    for required in ("title", "description", "priority"):
        if required in fields and fields[required] is None:
            raise HTTPException(status_code=422, detail=f"{required} cannot be empty")
    try:
        svc.update_fields(db, ticket, actor=user, fields=fields)
    except TicketError as e:
        _raise(e)
    db.commit()
    db.refresh(ticket)
    return detail_out(ticket, user)


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------
@router.post("/{ticket_id}/transitions", response_model=TicketDetailOut)
def transition_ticket(
    ticket_id: int, payload: TransitionIn, user: User = Depends(get_org_user), db: Session = Depends(get_db)
):
    ticket = _load(db, ticket_id, user)
    try:
        to_status = TicketStatus(payload.to_status)
    except ValueError:
        raise HTTPException(status_code=422, detail="Unknown status") from None
    try:
        svc.transition(
            db, ticket, to_status, actor=user, reason=payload.reason, resolution_summary=payload.resolution_summary
        )
    except TicketError as e:
        _raise(e)
    db.commit()
    db.refresh(ticket)
    return detail_out(ticket, user)


@router.post("/{ticket_id}/assign", response_model=TicketDetailOut)
def assign_ticket(ticket_id: int, payload: AssignIn, user: User = Depends(get_org_user), db: Session = Depends(get_db)):
    ticket = _load(db, ticket_id, user)
    if not has_permission(user.role, P.TICKETS_ASSIGN):
        # Agents may take an unassigned ticket or hand back their own.
        self_service = has_permission(user.role, P.TICKETS_WORK) and (
            (payload.assignee_id == user.id and ticket.assigned_to_user_id in (None, user.id))
            or (payload.assignee_id is None and ticket.assigned_to_user_id == user.id)
        )
        if not self_service or payload.team_id not in (None, ticket.team_id):
            raise HTTPException(status_code=403, detail="Only managers can assign tickets to other people")
    try:
        svc.assign(
            db, ticket, assignee_id=payload.assignee_id, team_id=payload.team_id, actor=user, reason=payload.reason
        )
    except TicketError as e:
        _raise(e)
    db.commit()
    db.refresh(ticket)
    return detail_out(ticket, user)


@router.post("/{ticket_id}/confirm-resolution", response_model=TicketDetailOut)
def confirm_resolution(
    ticket_id: int, payload: ConfirmResolutionIn, user: User = Depends(get_org_user), db: Session = Depends(get_db)
):
    ticket = _load(db, ticket_id, user)
    if ticket.created_by_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the requester can confirm a resolution")
    if ticket.status != TicketStatus.RESOLVED.value:
        raise HTTPException(status_code=409, detail="This ticket is not awaiting confirmation")
    try:
        if payload.accepted:
            svc.transition(
                db,
                ticket,
                TicketStatus.CLOSED,
                actor=user,
                reason=payload.reason or "Requester confirmed the resolution",
            )
        else:
            svc.transition(db, ticket, TicketStatus.REOPENED, actor=user, reason=payload.reason)
    except TicketError as e:
        _raise(e)
    db.commit()
    db.refresh(ticket)
    return detail_out(ticket, user)


@router.get("/{ticket_id}/history", response_model=list[StatusHistoryOut])
def ticket_history(ticket_id: int, user: User = Depends(get_org_user), db: Session = Depends(get_db)):
    ticket = _load(db, ticket_id, user)
    rows = (
        db.query(TicketStatusHistory)
        .options(joinedload(TicketStatusHistory.actor))
        .filter(TicketStatusHistory.ticket_id == ticket.id, TicketStatusHistory.tenant_id == ticket.tenant_id)
        .order_by(TicketStatusHistory.created_at.asc(), TicketStatusHistory.id.asc())
        .all()
    )
    out = [StatusHistoryOut.model_validate(r) for r in rows]
    if not (is_staff(user.role) or user.role == "analyst"):
        # Reasons can carry internal context (escalation notes, triage rules);
        # requesters only see the ones written for them.
        for item in out:
            if item.to_status not in _REQUESTER_VISIBLE_REASONS:
                item.reason = None
    return out


_REQUESTER_VISIBLE_REASONS = frozenset({"submitted", "waiting_for_customer", "resolved", "closed", "reopened"})


# ---------------------------------------------------------------------------
# Comments & attachments
# ---------------------------------------------------------------------------
def _visible_attachments_query(db: Session, ticket: Ticket, user: User):
    q = (
        db.query(Attachment)
        .options(joinedload(Attachment.uploaded_by))
        .filter(Attachment.ticket_id == ticket.id, Attachment.tenant_id == ticket.tenant_id)
    )
    if not (is_staff(user.role) or user.role == "analyst"):
        # Requesters never see files attached to internal notes.
        q = q.outerjoin(TicketComment, TicketComment.id == Attachment.comment_id).filter(
            or_(Attachment.comment_id.is_(None), TicketComment.visibility == "public")
        )
    return q.order_by(Attachment.created_at.asc(), Attachment.id.asc())


@router.get("/{ticket_id}/comments", response_model=list[CommentOut])
def list_comments(ticket_id: int, user: User = Depends(get_org_user), db: Session = Depends(get_db)):
    ticket = _load(db, ticket_id, user)
    comments = svc.visible_comments_query(db, ticket, user).options(joinedload(TicketComment.author)).all()
    by_comment: dict[int, list] = {}
    for a in _visible_attachments_query(db, ticket, user).filter(Attachment.comment_id.isnot(None)):
        by_comment.setdefault(a.comment_id, []).append(a)
    return [
        CommentOut.model_validate(
            {
                "id": c.id,
                "ticket_id": c.ticket_id,
                "visibility": c.visibility,
                "content": c.content,
                "author": c.author,
                "attachments": by_comment.get(c.id, []),
                "created_at": c.created_at,
            }
        )
        for c in comments
    ]


@router.post("/{ticket_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
def add_comment(
    request: Request,
    ticket_id: int,
    payload: CommentCreate,
    user: User = Depends(get_org_user),
    db: Session = Depends(get_db),
):
    ticket = _load(db, ticket_id, user)
    try:
        comment = svc.add_comment(db, ticket, author=user, content=payload.content, visibility=payload.visibility)
    except TicketError as e:
        _raise(e)
    db.commit()
    db.refresh(comment)
    return CommentOut.model_validate(
        {
            "id": comment.id,
            "ticket_id": comment.ticket_id,
            "visibility": comment.visibility,
            "content": comment.content,
            "author": comment.author,
            "attachments": [],
            "created_at": comment.created_at,
        }
    )


@router.get("/{ticket_id}/attachments", response_model=list[AttachmentOut])
def list_attachments(ticket_id: int, user: User = Depends(get_org_user), db: Session = Depends(get_db)):
    ticket = _load(db, ticket_id, user)
    return _visible_attachments_query(db, ticket, user).all()


@router.post("/{ticket_id}/attachments", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
def upload_attachment(
    request: Request,
    ticket_id: int,
    file: UploadFile = File(...),
    comment_id: int | None = Form(default=None),
    user: User = Depends(get_org_user),
    db: Session = Depends(get_db),
):
    ticket = _load(db, ticket_id, user)
    if not (is_staff(user.role) or ticket.created_by_user_id == user.id):
        raise HTTPException(status_code=403, detail="Only the requester or support staff can attach files")
    if ticket.status == TicketStatus.CLOSED.value and not is_staff(user.role):
        raise HTTPException(status_code=409, detail="This ticket is closed")
    if comment_id is not None:
        comment = (
            db.query(TicketComment).filter(TicketComment.id == comment_id, TicketComment.ticket_id == ticket.id).first()
        )
        if comment is None or comment.author_user_id != user.id:
            raise HTTPException(status_code=404, detail="Comment not found")

    data = file.file.read(settings.attachment_max_bytes + 1)
    try:
        filename, content_type = validate_upload(file.filename or "", data)
    except UploadRejected as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

    storage = get_storage()
    key = storage.save(ticket.tenant_id, data)
    att = Attachment(
        tenant_id=ticket.tenant_id,
        ticket_id=ticket.id,
        comment_id=comment_id,
        uploaded_by_user_id=user.id,
        filename=filename,
        content_type=content_type,
        size_bytes=len(data),
        sha256=sha256(data),
        storage_key=key,
    )
    db.add(att)
    try:
        db.flush()
        audit.record(
            db,
            "attachment.upload",
            tenant_id=ticket.tenant_id,
            actor=user,
            entity_type="attachment",
            entity_id=att.id,
            changes={"ticket_id": ticket.id, "filename": filename, "size": len(data)},
        )
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(key)
        raise
    db.refresh(att)
    return att


attachments_router = APIRouter(prefix="/attachments", tags=["tickets"])


@attachments_router.get("/{attachment_id}/download")
def download_attachment(attachment_id: int, user: User = Depends(get_org_user), db: Session = Depends(get_db)):
    att = db.query(Attachment).filter(Attachment.id == attachment_id, Attachment.tenant_id == user.tenant_id).first()
    if att is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    ticket = _load(db, att.ticket_id, user)
    if not _visible_attachments_query(db, ticket, user).filter(Attachment.id == att.id).first():
        raise HTTPException(status_code=404, detail="Attachment not found")
    data = get_storage().read(att.storage_key)
    return Response(
        content=data,
        media_type=att.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{att.filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
