import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.enums import ASSIGNABLE_GLOBAL_ROLES, GlobalRole
from app.common.validation import check_date, clean_email, clean_text


def _assignable(role: GlobalRole) -> GlobalRole:
    if role not in ASSIGNABLE_GLOBAL_ROLES:
        allowed = ", ".join(r.value for r in ASSIGNABLE_GLOBAL_ROLES)
        raise ValueError(f"role must be one of: {allowed}.")
    return role


class AdminUserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=200)
    email: str = Field(max_length=320)
    role: GlobalRole
    join_date: date | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return clean_text(value, label="Name")

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return clean_email(value)

    @field_validator("role")
    @classmethod
    def _role(cls, value: GlobalRole) -> GlobalRole:
        return _assignable(value)

    @field_validator("join_date")
    @classmethod
    def _join_date(cls, value: date | None) -> date | None:
        return check_date(value, "join_date")


class AdminUserUpdate(BaseModel):
    """Only the fields that are sent change. `join_date: null` clears the date."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    role: GlobalRole | None = None
    join_date: date | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return None if value is None else clean_text(value, label="Name")

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        return None if value is None else clean_email(value)

    @field_validator("role")
    @classmethod
    def _role(cls, value: GlobalRole | None) -> GlobalRole | None:
        return None if value is None else _assignable(value)

    @field_validator("join_date")
    @classmethod
    def _join_date(cls, value: date | None) -> date | None:
        return check_date(value, "join_date")

    @model_validator(mode="after")
    def _required_fields_not_null(self) -> "AdminUserUpdate":
        for field in ("name", "email", "role"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} must not be null.")
        return self


class AdminProjectOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class AdminUserOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: str
    is_active: bool
    join_date: date | None
    password_set: bool = Field(description="False until the person has used an invite link.")
    invite_pending: bool = Field(description="A link exists that has not been used or expired.")
    projects: list[AdminProjectOut] = Field(description="Active projects the person belongs to.")
    created_at: datetime


class AdminUserListOut(BaseModel):
    items: list[AdminUserOut]
    total: int = Field(description="Users matching the filters.")
    active_total: int = Field(description="Of those, how many are active.")
    page: int
    page_size: int


class InviteOut(BaseModel):
    url: str = Field(description="Hand this to the person. It is shown only once.")
    expires_at: datetime


class AdminUserCreatedOut(BaseModel):
    user: AdminUserOut
    invite: InviteOut
