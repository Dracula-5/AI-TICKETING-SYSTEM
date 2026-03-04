from pydantic import BaseModel, Field
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
    pricing_status: str = "pending"
    final_price: float | None = None
    price_finalized_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class BargainingOfferIn(BaseModel):
    amount: float = Field(..., gt=0)
    message: Optional[str] = None


class BargainingActionIn(BaseModel):
    negotiation_id: Optional[int] = None
    message: Optional[str] = None


class BargainingEntryOut(BaseModel):
    id: int
    ticket_id: int
    sender_user_id: int
    sender_role: str
    action: str
    amount: float
    message: str | None = None
    is_final: bool
    created_at: datetime

    class Config:
        from_attributes = True


class BargainingMonitorOut(BaseModel):
    ticket_id: int
    ticket_title: str
    ticket_status: str
    pricing_status: str
    final_price: float | None = None
    last_action: str | None = None
    last_amount: float | None = None
    last_sender_role: str | None = None
    last_created_at: datetime | None = None


class BargainingActionOut(BaseModel):
    message: str
    pricing_status: str
    final_price: float | None = None
    negotiation: BargainingEntryOut
