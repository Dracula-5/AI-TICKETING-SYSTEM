from pydantic import BaseModel
from datetime import datetime


class CommentCreate(BaseModel):
    ticket_id: int
    content: str


class CommentOut(BaseModel):
    id: int
    ticket_id: int
    content: str
    created_at: datetime

    class Config:
        from_attributes = True
        orm_mode = True









