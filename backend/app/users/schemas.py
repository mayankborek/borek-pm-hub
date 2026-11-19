import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.common.validation import clean_phone
from app.organisations.schemas import OrganisationBrief


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


class ProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: str
    job_title: str | None
    phone: str | None
    organisation: OrganisationBrief | None


class ProfileUpdate(BaseModel):
    """Only the phone number is the person's own to change; name, email, role and job title are
    managed by the administrator."""

    model_config = ConfigDict(extra="forbid")

    phone: str | None = Field(default=None, max_length=50, description='null or "" clears it.')

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        return clean_phone(value)
