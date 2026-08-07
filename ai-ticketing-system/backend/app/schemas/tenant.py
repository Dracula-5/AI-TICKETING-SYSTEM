from pydantic import BaseModel, ConfigDict


class TenantCreate(BaseModel):
    name: str
    domain: str


class TenantOut(TenantCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
