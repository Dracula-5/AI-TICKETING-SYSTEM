from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime

from app.schemas.vendors import VendorPublicOut


def _validate_image_urls(urls: list[str]) -> list[str]:
    for url in urls:
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError(f"Invalid image URL {url!r}: must start with http:// or https://")
    return urls


class ProductImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    sort_order: int


class ProductCreate(BaseModel):
    title: str
    description: str
    price: float = Field(..., gt=0)
    currency: str = "INR"
    stock_quantity: int = Field(0, ge=0)
    image_urls: list[str] = Field(default_factory=list)

    @field_validator("image_urls")
    @classmethod
    def check_image_urls(cls, value: list[str]) -> list[str]:
        return _validate_image_urls(value)


class ProductUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    price: float | None = Field(None, gt=0)
    currency: str | None = None
    stock_quantity: int | None = Field(None, ge=0)
    image_urls: list[str] | None = None

    @field_validator("image_urls")
    @classmethod
    def check_image_urls(cls, value: list[str] | None) -> list[str] | None:
        return _validate_image_urls(value) if value is not None else value


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    vendor_id: int
    title: str
    description: str
    category: str | None = None
    price: float
    currency: str
    stock_quantity: int
    status: str
    views_count: int
    created_at: datetime
    updated_at: datetime | None = None
    images: list[ProductImageOut] = Field(default_factory=list)
    vendor: VendorPublicOut


class ProductListOut(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    page_size: int
