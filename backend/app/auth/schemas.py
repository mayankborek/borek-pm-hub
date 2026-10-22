import uuid

from pydantic import BaseModel, ConfigDict, Field


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


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Seconds until the token expires.")
    user: UserOut
