import uuid

from pydantic import BaseModel, ConfigDict


class UserListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    role: str  # "pm" | "developer"


class UserListOut(BaseModel):
    items: list[UserListItem]
    total: int
    page: int
    page_size: int
