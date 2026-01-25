from pydantic import BaseModel

class TenantCreate(BaseModel):
    name: str
    domain: str

class TenantOut(TenantCreate):
    id: int

    class Config:
        from_attributes = True
