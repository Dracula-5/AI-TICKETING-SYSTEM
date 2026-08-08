from pydantic import BaseModel, ConfigDict, EmailStr, Field

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str
    tenant_id: int

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    role: str
    tenant_id: int


class UserUpdate(BaseModel):
    """Self-service profile edit. No role/tenant_id -- those must never be
    user-editable (privilege escalation / tenant-isolation risk)."""
    name: str | None = None
    email: EmailStr | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)
