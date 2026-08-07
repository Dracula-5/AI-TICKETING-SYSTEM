from pydantic import BaseModel, ConfigDict, EmailStr

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
