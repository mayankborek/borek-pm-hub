import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.common.enums import OrganisationType
from app.common.validation import clean_text

MAX_ACCOUNT_MANAGERS = 50


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
