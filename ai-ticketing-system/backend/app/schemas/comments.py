from datetime import datetime
from pydantic import BaseModel, ConfigDict


class CommentCreate(BaseModel):
    content: str


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    content: str
    created_at: datetime
