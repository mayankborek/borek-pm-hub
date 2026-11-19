"""What the client portal returns. These shapes are separate from the internal ones on purpose:
only fields listed here ever reach a client (no tasks, effort, activity, drafts or money)."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.common.enums import ProjectStatus, RagStatus

ClientHealth = Literal["on_track", "at_risk", "off_track"]

HEALTH_OF_RAG: dict[str, ClientHealth] = {
    RagStatus.GREEN.value: "on_track",
    RagStatus.AMBER.value: "at_risk",
    RagStatus.RED.value: "off_track",
}


class ClientOrganisationOut(BaseModel):
    id: uuid.UUID
    name: str


class PublishedBy(BaseModel):
    name: str
    role: str = Field(description="For example Project Manager.")


class LatestUpdate(BaseModel):
    text: str = Field(description="Summary of the newest published status report.")
    date: date
    report_id: uuid.UUID


class ClientProjectOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    category: str | None
    status: ProjectStatus
    start_date: date | None
    due_date: date | None = Field(description="The project's target end date.")
    health: ClientHealth | None = Field(
        description="From the newest published status report (green/amber/red); null until the "
        "first report is published."
    )
    progress: int = Field(description="Share of the project's tasks that are done, 0-100.")
    published_on: date | None = Field(description="Date of the newest published status report.")
    published_by: PublishedBy | None
    latest_update: LatestUpdate | None


class ClientContactOut(BaseModel):
    name: str
    role: str = Field(description="Project Manager, Account Manager or the stakeholder's role.")
    email: str | None
    phone: str | None


class ClientReportBrief(BaseModel):
    id: uuid.UUID
    title: str
    report_date: date
    health: ClientHealth
    summary: str
    published_at: datetime


class ClientReportOut(ClientReportBrief):
    achievements: str | None
    next_steps: str | None
    risks: str | None
    published_by: PublishedBy | None
    project_id: uuid.UUID
    project_name: str


class ClientProjectDetailOut(ClientProjectOut):
    description: str | None
    contacts: list[ClientContactOut]
    reports: list[ClientReportBrief] = Field(description="Published reports, newest first.")


class ClientUpdateOut(BaseModel):
    """A recent published report, for the dashboard's "latest updates"."""

    report_id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    title: str
    published_at: datetime


class ClientPortalOut(BaseModel):
    organisation: ClientOrganisationOut | None
    projects: list[ClientProjectOut]
    updates: list[ClientUpdateOut] = Field(description="Newest published reports, at most 10.")
    summary: dict[str, int] = Field(
        description="Projects per health (on_track, at_risk, off_track, none) and `total`."
    )
