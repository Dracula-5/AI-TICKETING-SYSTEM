# backend/app/schemas/schemas.py
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


# ---------------- Tenant Schemas ----------------
class TenantBase(BaseModel):
    name: str
    domain: str


class TenantCreate(TenantBase):
    pass


class TenantResponse(TenantBase):
    id: int

    class Config:
        from_attributes = True  # allows SQLAlchemy models to be returned as Pydantic models


# ---------------- User Schemas ----------------
class UserBase(BaseModel):
    name: str
    email: EmailStr
    role: Optional[str] = "user"


class UserCreate(UserBase):
    password: str  # plain password, will hash before saving


class UserResponse(UserBase):
    id: int
    tenant_id: Optional[int]

    class Config:
        from_attributes = True


# ---------------- Ticket Comment Schemas ----------------
class TicketCommentBase(BaseModel):
    content: str


class TicketCommentCreate(TicketCommentBase):
    pass


class TicketCommentResponse(TicketCommentBase):
    id: int
    ticket_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------- Ticket Schemas ----------------
class TicketBase(BaseModel):
    title: str
    description: str
    priority: Optional[str] = "medium"
    status: Optional[str] = "open"


class TicketCreate(TicketBase):
    pass


class TicketUpdate(BaseModel):
    title: Optional[str]
    description: Optional[str]
    priority: Optional[str]
    status: Optional[str]


class TicketResponse(TicketBase):
    id: int
    tenant_id: Optional[int]
    created_by_user_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    comments: List[TicketCommentResponse] = []

    class Config:
        from_attributes = True
