from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.users import UserBrief

Priority = Literal["low", "medium", "high", "critical"]


class TicketCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=1, max_length=10_000)
    priority: Priority | None = None
    category: str | None = Field(default=None, max_length=80)


class TicketUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=10_000)
    priority: Priority | None = None
    category: str | None = Field(default=None, max_length=80)
    team_id: int | None = None


class TransitionIn(BaseModel):
    to_status: str
    reason: str | None = Field(default=None, max_length=2000)
    resolution_summary: str | None = Field(default=None, max_length=5000)


class AssignIn(BaseModel):
    assignee_id: int | None = None
    team_id: int | None = None
    reason: str | None = Field(default=None, max_length=500)


class ConfirmResolutionIn(BaseModel):
    accepted: bool
    reason: str | None = Field(default=None, max_length=2000)


class TeamBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class SlaState(BaseModel):
    first_response_due: datetime | None
    first_responded_at: datetime | None
    first_response_breached: bool
    resolution_due: datetime | None
    resolution_breached: bool
    paused: bool
    # ok | at_risk | breached | paused | met | none
    state: str


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: int
    title: str
    description: str
    priority: str
    category: str | None
    status: str
    channel: str
    triage_source: str | None
    requester: UserBrief
    assignee: UserBrief | None
    team: TeamBrief | None
    sla: SlaState
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    reopened_count: int
    resolution_summary: str | None
    data_origin: str
    created_at: datetime
    updated_at: datetime


class TicketDetailOut(TicketOut):
    allowed_transitions: list[str]
    can_assign: bool
    can_edit: bool


class StatusHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_status: str | None
    to_status: str
    actor_type: str
    actor: UserBrief | None
    reason: str | None
    created_at: datetime


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10_000)
    visibility: Literal["public", "internal"] = "public"


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    comment_id: int | None
    filename: str
    content_type: str
    size_bytes: int
    uploaded_by: UserBrief
    created_at: datetime


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    visibility: str
    content: str
    author: UserBrief | None
    attachments: list[AttachmentOut] = Field(default_factory=list)
    created_at: datetime
