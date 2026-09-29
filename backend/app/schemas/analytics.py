from datetime import date, datetime

from pydantic import BaseModel


class CountItem(BaseModel):
    key: str | None
    count: int


class WorkloadItem(BaseModel):
    id: int | None
    name: str
    open: int


class TrendPoint(BaseModel):
    day: date
    created: int
    resolved: int


class OverviewOut(BaseModel):
    generated_at: datetime
    data_origin: str  # "demo" when computed over a demo organization
    open_tickets: int
    created_today: int
    unassigned_open: int
    sla_breached_open: int
    sla_at_risk_open: int
    resolved_last_30d: int
    avg_first_response_minutes_30d: float | None
    avg_resolution_hours_30d: float | None
    sla_compliance_pct_30d: float | None
    reopen_rate_pct_30d: float | None
    by_status: list[CountItem]
    by_priority: list[CountItem]
    by_category: list[CountItem]
    by_team: list[WorkloadItem]
    by_agent: list[WorkloadItem]
    trend_14d: list[TrendPoint]


class AuditLogOut(BaseModel):
    id: int
    actor_type: str
    actor_name: str | None
    actor_email: str | None
    action: str
    entity_type: str | None
    entity_id: str | None
    changes: dict | None
    ip: str | None
    request_id: str | None
    created_at: datetime


class PlatformOverviewOut(BaseModel):
    organizations: int
    demo_organizations: int
    users_by_origin: dict[str, int]
    tickets_by_origin: dict[str, int]
    active_users_7d_real: int
