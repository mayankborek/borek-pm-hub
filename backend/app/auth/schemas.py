import uuid

from pydantic import BaseModel, ConfigDict


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    role: str  # "pm" | "developer"


class MembershipOut(BaseModel):
    project_id: uuid.UUID
    project_code: str
    project_name: str
    project_role: str


class MeOut(UserOut):
    is_active: bool
    memberships: list[MembershipOut]
