from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.ai.rules import PRIORITIES


class OrgSettings(BaseModel):
    auto_assign: bool = False
    auto_close_days: int = Field(default=3, ge=1, le=60)
    reopen_window_days: int = Field(default=14, ge=0, le=365)
    portal_signup_enabled: bool = False
    portal_allowed_domains: list[str] = Field(default_factory=list, max_length=20)
    ai_auto_apply_kinds: list[Literal["category", "priority", "team", "assignee"]] = Field(default_factory=list)
    ai_auto_apply_threshold: float = Field(default=0.9, ge=0.5, le=1.0)
    ai_duplicate_threshold: float = Field(default=0.75, ge=0.5, le=1.0)
    ai_min_history: int = Field(default=5, ge=1, le=100)
    ai_llm_monthly_token_budget: int = Field(default=1_000_000, ge=0, le=1_000_000_000)

    @field_validator("portal_allowed_domains")
    @classmethod
    def _domains(cls, value: list[str]) -> list[str]:
        cleaned = sorted({d.strip().lower().lstrip("@") for d in value if d.strip()})
        for d in cleaned:
            if "." not in d or " " in d or len(d) > 253:
                raise ValueError(f"Invalid domain: {d}")
        return cleaned


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    is_demo: bool
    settings: OrgSettings
    created_at: datetime


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    settings: OrgSettings | None = None


class PortalInfoOut(BaseModel):
    name: str
    slug: str
    signup_enabled: bool
    allowed_domains: list[str]


class InvitationCreate(BaseModel):
    email: EmailStr
    role: str
    team_id: int | None = None


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: str
    team_id: int | None
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class InvitationCreatedOut(InvitationOut):
    # Returned once, to the inviter, so the link can be shared directly when
    # email delivery isn't configured. Never stored in plain text.
    invite_url: str


class TeamIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    member_ids: list[int] = Field(default_factory=list)


class TeamMembersIn(BaseModel):
    user_ids: list[int] = Field(max_length=500)


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    keywords: list[str] = Field(default_factory=list, max_length=100)
    default_team_id: int | None = None
    is_active: bool = True

    @field_validator("keywords")
    @classmethod
    def _keywords(cls, value: list[str]) -> list[str]:
        return sorted({k.strip().lower() for k in value if k.strip()})[:100]


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    keywords: list[str]
    default_team_id: int | None
    is_active: bool


class SlaPolicyItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    priority: str
    first_response_minutes: int = Field(ge=1, le=60 * 24 * 30)
    resolution_minutes: int = Field(ge=1, le=60 * 24 * 90)

    @field_validator("priority")
    @classmethod
    def _priority(cls, value: str) -> str:
        if value not in PRIORITIES:
            raise ValueError(f"priority must be one of {PRIORITIES}")
        return value


class SlaPoliciesIn(BaseModel):
    policies: list[SlaPolicyItem]
