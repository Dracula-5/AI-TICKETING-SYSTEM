from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime

from app.schemas.products import ProductOut


class NegotiationStart(BaseModel):
    product_id: int
    amount: float = Field(..., gt=0)
    message: str | None = None


class NegotiationMessageIn(BaseModel):
    """Shape of a single WebSocket-inbound chat event."""
    type: str  # text | offer | accept | reject
    amount: float | None = None
    text: str | None = None


class NegotiationMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    sender_role: str
    sender_user_id: int | None = None
    message_type: str
    amount: float | None = None
    text_content: str | None = None
    created_at: datetime


class NegotiationSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    product_id: int
    customer_id: int
    vendor_id: int
    status: str
    current_offer_price: float | None = None
    created_at: datetime
    closed_at: datetime | None = None
    product: ProductOut
    messages: list[NegotiationMessageOut] = Field(default_factory=list)


class NegotiationSessionSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    customer_id: int
    vendor_id: int
    status: str
    current_offer_price: float | None = None
    created_at: datetime
    product: ProductOut
