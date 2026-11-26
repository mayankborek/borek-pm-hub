import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.common.enums import OrganisationType
from app.common.validation import clean_email, clean_optional_text, clean_text

MAX_ACCOUNT_MANAGERS = 50
MAX_NEW_CONTACTS = 20
MAX_PROJECT_CONTACTS = 20

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


def clean_job_title(value: str | None) -> str | None:
    """Trimmed, one line; empty means no job title."""
    return clean_optional_text(value, max_length=100, label="Job title", multiline=False)


def _clean_industry(value: str | None) -> str | None:
    return clean_optional_text(value, max_length=100, label="Industry", multiline=False)


def _clean_website(value: str | None) -> str | None:
    """Optional; http(s) address. A bare domain gets https:// in front."""
    text = clean_optional_text(value, max_length=300, label="Website", multiline=False)
    if text is None:
        return None
    if "://" not in text:
        text = f"https://{text}"
    scheme, _, rest = text.partition("://")
    host = rest.split("/", 1)[0]
    if scheme.lower() not in ("http", "https") or "." not in host or " " in text:
        raise ValueError("Enter a web address such as https://example.com.")
    return text


def _clean_optional_email(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return clean_email(value)


class _OrganisationDetails(BaseModel):
    """Setup details from the Administrator handoff. All optional."""

    industry: str | None = Field(default=None, max_length=100)
    website: str | None = Field(default=None, max_length=300)
    primary_contact_email: str | None = Field(default=None, max_length=320)
    project_manager_id: uuid.UUID | None = Field(
        default=None, description="Optional Project Manager (an active PM) for this client."
    )

    _industry = field_validator("industry")(_clean_industry)
    _website = field_validator("website")(_clean_website)
    _primary = field_validator("primary_contact_email")(_clean_optional_email)


class OrganisationCreate(_OrganisationDetails):
    """One call sets up the whole client (handoff 07): details, Account Managers, optional PM
    and the first client accounts. All or nothing."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=200)
    type: OrganisationType = OrganisationType.CLIENT
    account_manager_ids: list[uuid.UUID] = Field(
        default_factory=list, max_length=MAX_ACCOUNT_MANAGERS
    )
    contacts: list["OrganisationMemberCreate"] = Field(
        default_factory=list,
        max_length=MAX_NEW_CONTACTS,
        description="Client accounts to create; each gets an invite link (returned once).",
    )

    _name = field_validator("name")(_clean_name)


class OrganisationUpdate(_OrganisationDetails):
    """Send only what changes. null or "" clears an optional detail. `account_manager_ids`
    replaces the whole list when sent."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1, description="Version from the last read (optimistic locking).")
    name: str | None = Field(default=None, max_length=200)
    account_manager_ids: list[uuid.UUID] | None = Field(
        default=None, max_length=MAX_ACCOUNT_MANAGERS
    )

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_name(value)


class OrganisationProject(BaseModel):
    """A project of this client with its named client contacts."""

    id: uuid.UUID
    code: str
    name: str
    contacts: list[PersonBrief]
    needs_contact: bool = Field(description='No named contact: show "Contact needs assignment".')


class OrganisationOut(BaseModel):
    id: uuid.UUID
    name: str
    type: OrganisationType
    archived_at: datetime | None
    version: int
    created_at: datetime
    account_managers: list[PersonBrief]
    industry: str | None = None
    website: str | None = None
    primary_contact_email: str | None = None
    project_manager: PersonBrief | None = None
    projects: list[OrganisationProject] = Field(
        default_factory=list, description='Active projects; empty = "No project yet".'
    )
    contact_count: int = Field(default=0, description="Active client accounts.")


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
    job_title: str | None = Field(default=None, max_length=100)

    _name = field_validator("name")(_clean_name)
    _job_title = field_validator("job_title")(clean_job_title)

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
    job_title: str | None
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


class OrganisationCreatedOut(OrganisationOut):
    contacts_created: list[OrganisationMemberCreatedOut] = Field(
        default_factory=list,
        description="The client accounts made in this call, with their invite links (once).",
    )


class ProjectContactsUpdate(BaseModel):
    """The complete list of a project's named client contacts (at least one)."""

    model_config = ConfigDict(extra="forbid")

    user_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_PROJECT_CONTACTS)


OrganisationCreate.model_rebuild()
