from pydantic import BaseModel


class ProviderCreate(BaseModel):
    name: str
    department: str
    contact: str


class ProviderOut(BaseModel):
    id: int
    name: str
    department: str
    contact: str
    tenant_id: int

    class Config:
        
        from_attributes = True