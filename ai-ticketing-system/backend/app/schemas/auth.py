from pydantic import BaseModel, EmailStr


# =========================
# REGISTER REQUEST
# =========================
class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str
    tenant_id: int


# =========================
# SIMPLE REGISTER REQUEST
# =========================
class RegisterSimpleRequest(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None
    role: str = "customer"
    tenant_id: int = 1


# =========================
# JWT TOKEN RESPONSE
# =========================
class Token(BaseModel):
    access_token: str
    token_type: str
