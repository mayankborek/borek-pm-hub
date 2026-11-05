import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from app.common.validation import has_control_chars


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    role: str  # "admin" | "pm" | "developer" (| "manager" | "account_manager" | "client" later)


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

    @field_validator("email")
    @classmethod
    def _plain_email(cls, value: str) -> str:
        if has_control_chars(value) or any(char.isspace() for char in value.strip()):
            raise ValueError("The email contains characters that are not allowed.")
        return value


NewPassword = Annotated[str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)]


class AcceptInviteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=20, max_length=200)
    password: NewPassword


class AcceptInviteOut(BaseModel):
    email: str = Field(description="The account's email, so the login page can be pre-filled.")


class ChangePasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=200)
    new_password: NewPassword


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Seconds until the token expires.")
    user: UserOut
