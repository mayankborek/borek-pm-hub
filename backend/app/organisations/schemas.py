import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.common.enums import OrganisationType
from app.common.validation import clean_email, clean_text

MAX_ACCOUNT_MANAGERS = 50

MemberStatus = Literal["invited", "invite_expired", "active", "deactivated"]


class OrganisationBrief(BaseModel):
    id: uuid.UUID
    name: str


class PersonBrief(BaseModel):
    id: uuid.UUID
    name: str
    email: str


def _clean_name(value: str) -> str:
    return clean_text(value, label="Name")


class OrganisationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=200)
    type: OrganisationType = OrganisationType.CLIENT

    _name = field_validator("name")(_clean_name)


class OrganisationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1, description="Version from the last read (optimistic locking).")
    name: str = Field(max_length=200)

    _name = field_validator("name")(_clean_name)


class OrganisationOut(BaseModel):
    id: uuid.UUID
    name: str
    type: OrganisationType
    archived_at: datetime | None
    version: int
    created_at: datetime
    account_managers: list[PersonBrief]


class OrganisationListOut(BaseModel):
    items: list[OrganisationOut]
    total: int
    page: int
    page_size: int


class AccountManagersUpdate(BaseModel):
    """The complete list: people left out stop being account managers of this organisation."""

    model_config = ConfigDict(extra="forbid")

    user_ids: list[uuid.UUID] = Field(max_length=MAX_ACCOUNT_MANAGERS)


# --- members (client contacts) ------------------------------------------------------------------


class OrganisationMemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=200)
    email: str = Field(max_length=320)

    _name = field_validator("name")(_clean_name)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return clean_email(value)


class OrganisationMemberOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: str = Field(description="`client` for contacts added here.")
    status: MemberStatus = Field(
        description="invited: link open, no password yet; invite_expired: no password and no "
        "usable link (create a new one); active: password set; deactivated: removed."
    )
    is_active: bool
    password_set: bool
    invite_pending: bool
    join_date: date | None
    created_at: datetime


class OrganisationMemberListOut(BaseModel):
    items: list[OrganisationMemberOut]
    total: int
    page: int
    page_size: int


class MemberInviteOut(BaseModel):
    url: str = Field(description="Hand this to the person. It is shown only once.")
    expires_at: datetime


class OrganisationMemberCreatedOut(BaseModel):
    member: OrganisationMemberOut
    invite: MemberInviteOut
