from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    title: str
    message: str | None = None
    link: str | None = None
    is_read: bool
    created_at: datetime


class UnreadCountOut(BaseModel):
    count: int


class ProviderCategoriesIn(BaseModel):
    categories: list[str] = Field(default_factory=list)


class ProviderCategoriesOut(BaseModel):
    categories: list[str]
