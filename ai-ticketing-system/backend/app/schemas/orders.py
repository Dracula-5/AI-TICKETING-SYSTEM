from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime


class OrderCreate(BaseModel):
    product_id: int
    quantity: int = Field(1, ge=1)
    negotiation_session_id: int | None = None
    delivery_address: str | None = None


class OrderProductSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    currency: str


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    product_id: int
    customer_id: int
    vendor_id: int
    negotiation_session_id: int | None = None
    quantity: int
    unit_price: float
    total_price: float
    status: str
    delivery_address: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    product: OrderProductSummary
