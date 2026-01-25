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
# JWT TOKEN RESPONSE
# =========================
class Token(BaseModel):
    access_token: str
    token_type: str
