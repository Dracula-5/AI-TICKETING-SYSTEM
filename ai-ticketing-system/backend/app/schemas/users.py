from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str
    tenant_id: int

class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str
    tenant_id: int

    class Config:
        from_attributes = True
