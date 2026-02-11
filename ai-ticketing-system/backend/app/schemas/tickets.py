from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class TicketCreate(BaseModel):
    title: str
    description: str
    priority: Optional[str] = None
    tenant_id: int


class TicketOut(BaseModel):
    id: int
    title: str
    description: str
    priority: str
    status: str
    tenant_id: int
    created_by_user_id: int
    category: str | None = None
    sla_due: datetime | None = None
    assigned_to_user_id: int | None = None
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        orm_mode = True
        from_attributes = True
