import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.auth.policy import Cell


class RoleCellOut(BaseModel):
    key: str
    label: str
    section: str
    value: Cell = Field(description="always / on / off / none (a dash: not configured here).")
    default: Cell
    editable: bool = Field(description="A switch the administrator can change.")


class RoleColumnOut(BaseModel):
    role: str
    label: str
    editable: bool = Field(description="False for Administrator and Client (fixed policy).")
    customised: bool = Field(description="Some value differs from the default (offer reset).")
    permissions: list[RoleCellOut]


class RoleMatrixOut(BaseModel):
    roles: list[RoleColumnOut]


class SwitchUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class PersonRef(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: str


class PersonProjectOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    access: Literal["project_lead", "developer", "account_manager", "manager"] = Field(
        description="Why the person reaches the project."
    )
    customised: bool = Field(description="The person has switches set in this project.")


class PersonProjectsOut(BaseModel):
    person: PersonRef
    editable: bool = Field(description="False for administrators and client contacts (fixed).")
    items: list[PersonProjectOut]


class ControlOut(BaseModel):
    key: str
    label: str
    enabled: bool = Field(description="What the person can do now.")
    default: bool = Field(description="What they could do without switches in this project.")
    customised: bool = Field(description="A switch is saved for this control.")
    editable: bool
    linked_with: list[str] = Field(
        description="Controls that switch the same server right: they change together."
    )


class SectionOut(BaseModel):
    key: str
    label: str
    customised: bool
    controls: list[ControlOut]


class ProjectRef(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class PersonProjectAccessOut(BaseModel):
    person: PersonRef
    project: ProjectRef
    access: Literal["project_lead", "developer", "account_manager", "manager"]
    sections: list[SectionOut]


class MyPermissionsOut(BaseModel):
    role: str
    permissions: dict[str, bool] = Field(
        description="Role matrix rows for the signed-in user (menus such as projects_menu)."
    )
