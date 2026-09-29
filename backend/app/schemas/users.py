from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrgSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    is_demo: bool


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: str
    tenant_id: int | None
    is_active: bool
    email_verified_at: datetime | None = None
    last_login_at: datetime | None = None
    created_at: datetime


class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: str


class MeOut(UserOut):
    organization: OrgSummary | None = None
    permissions: list[str]
    team_ids: list[int]


class ProfileUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class MemberUpdate(BaseModel):
    role: str | None = None
    is_active: bool | None = None
