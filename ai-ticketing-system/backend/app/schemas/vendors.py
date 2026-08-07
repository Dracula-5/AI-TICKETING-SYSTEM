from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
from datetime import datetime

from app.core.constants import MARKETPLACE_CATEGORIES


class VendorRegister(BaseModel):
    name: str
    email: EmailStr
    password: str
    tenant_id: int
    shop_name: str
    phone_number: str
    shop_address: str
    description: str | None = None
    category: str

    @field_validator("category")
    @classmethod
    def check_category(cls, value: str) -> str:
        if value not in MARKETPLACE_CATEGORIES:
            raise ValueError(f"category must be one of {MARKETPLACE_CATEGORIES}")
        return value


class VendorUpdate(BaseModel):
    shop_name: str | None = None
    phone_number: str | None = None
    shop_address: str | None = None
    description: str | None = None


class VendorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    tenant_id: int
    shop_name: str
    phone_number: str
    shop_address: str
    description: str | None = None
    category: str | None = None
    is_verified: bool
    rating_avg: float
    created_at: datetime


class VendorPublicOut(BaseModel):
    """Shop profile shown to customers on a product page — no user_id/tenant_id leakage."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    shop_name: str
    phone_number: str
    shop_address: str
    description: str | None = None
    category: str | None = None
    is_verified: bool
    rating_avg: float


class CategoryAvailabilityOut(BaseModel):
    category: str
    available: bool
    shop_name: str | None = None
