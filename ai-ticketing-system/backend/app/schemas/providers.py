from pydantic import BaseModel, ConfigDict


class ProviderCreate(BaseModel):
    name: str
    department: str
    contact: str


class ProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    department: str
    contact: str
    tenant_id: int
