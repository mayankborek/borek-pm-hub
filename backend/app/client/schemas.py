"""What the client portal returns. These shapes are separate from the internal ones on purpose:
only fields listed here ever reach a client (no tasks, effort, activity, drafts or money)."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.change_requests.models import ChangeRequestStatus
from app.common.enums import ImpactUnit, ProjectStatus, RagStatus
from app.milestones.schemas import MilestoneState, PhaseStatus

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


class ClientMilestoneOut(BaseModel):
    """A milestone the PM marked visible to the client. No owner, criteria or task details."""

    id: uuid.UUID
    code: str
    name: str
    due_date: date
    state: MilestoneState
    progress: int | None = Field(
        description="100 once reached, else null = not available. Never task-based for clients."
    )
    completed_on: date | None = Field(description="When it was reached; null while open.")
    original_due_date: date | None = Field(
        description="The date before an approved change request moved it (state revised)."
    )
    requested_date: date | None = Field(
        description="A new date asked for by a change request still in review."
    )
    change_request_code: str | None


class NextMilestone(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    due_date: date
    state: MilestoneState


class ClientPersonOut(BaseModel):
    name: str
    email: str | None


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
    progress: int | None = Field(
        description="Progress the PM published (newest published report that shares one), "
        "0-100. Null = not published yet (show 'Progress not published yet', never 0%)."
    )
    progress_published_on: date | None = Field(
        description="Date of the report that published `progress`."
    )
    published_on: date | None = Field(description="Date of the newest published status report.")
    published_by: PublishedBy | None
    latest_update: LatestUpdate | None
    awaiting_input: int = Field(
        description="Client actions: requirements of this project waiting for your answer."
    )
    project_manager: ClientPersonOut | None = Field(
        description="The project lead; null = Project Manager not assigned yet."
    )
    next_milestone: NextMilestone | None = Field(
        description="The earliest visible milestone that is not done yet."
    )


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
    progress: int | None = Field(description="Progress shared in this report, if any.")
    summary: str
    published_at: datetime


class ClientReportOut(ClientReportBrief):
    achievements: str | None
    next_steps: str | None
    risks: str | None
    published_by: PublishedBy | None
    project_id: uuid.UUID
    project_name: str


class ClientUpdateOut(BaseModel):
    """A client-visible event: a published report, a change request raised, taken into review
    or decided, or a shared milestone shared ("Milestone schedule published") or reached.
    For "Recent updates" (dashboard) and "Recent activity" (overview)."""

    kind: Literal["report", "change_request", "milestone"]
    project_id: uuid.UUID
    project_name: str
    title: str = Field(description="Report title, or the code and title / name of the item.")
    occurred_at: datetime
    report_id: uuid.UUID | None = Field(description="For kind report.")
    change_request_id: uuid.UUID | None = Field(description="For kind change_request.")
    milestone_id: uuid.UUID | None = Field(default=None, description="For kind milestone.")
    due_date: date | None = Field(default=None, description="For kind milestone.")
    status: ChangeRequestStatus | Literal["shared", "done"] | None = Field(
        description="change_request: the status this event set (pending = raised); "
        'milestone: shared ("Milestone schedule published") or done; report: null.'
    )


class ClientChangeRequestBrief(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    status: ChangeRequestStatus


class ClientMilestoneRef(BaseModel):
    code: str
    name: str


class ClientChangeRequestOut(ClientChangeRequestBrief):
    """No effort hours and no internal people: what the client may see of a request."""

    description: str
    reason: str | None
    milestone: ClientMilestoneRef | None = Field(description="Only if shown to the client.")
    requested_date: date | None
    review_started_at: datetime | None = Field(description="For the request timeline.")
    impact_schedule_value: int | None = Field(
        description="How far the delivery moves, in impact_schedule_unit (minus = earlier)."
    )
    impact_schedule_unit: ImpactUnit | None
    impact_scope: str | None
    decision_note: str | None
    decided_at: datetime | None
    submitted_by: str = Field(description="Name of the person who raised it.")
    submitted_at: datetime


class ClientChangeRequestListOut(BaseModel):
    items: list[ClientChangeRequestOut] = Field(description="Newest first.")
    counts: dict[str, int] = Field(
        description="Requests per status (pending, in_review, approved, declined) and `total`."
    )


class ClientProjectDetailOut(ClientProjectOut):
    description: str | None
    contacts: list[ClientContactOut]
    reports: list[ClientReportBrief] = Field(description="Published reports, newest first.")
    milestones: list[ClientMilestoneOut] = Field(description="Visible milestones, by due date.")
    change_requests: list[ClientChangeRequestBrief] = Field(description="Newest first.")
    activity: list[ClientUpdateOut] = Field(description="Newest events first, at most 10.")


class ClientKpis(BaseModel):
    """The four dashboard numbers, over the client's authorized projects."""

    active_projects: int = Field(description="Not completed and not cancelled.")
    awaiting_input: int = Field(
        description="Requirements whose current version waits for the client's answer."
    )
    upcoming_milestones: int = Field(description="Shared, open, due in the next 14 days.")
    shared_reports: int = Field(description="Published reports.")


class ClientLatestReport(ClientReportBrief):
    project_id: uuid.UUID
    project_name: str


class ClientUpcomingMilestone(ClientMilestoneOut):
    project_id: uuid.UUID
    project_name: str


class ClientPhaseOut(BaseModel):
    """A phase bar on the client's roadmap."""

    id: uuid.UUID
    name: str
    start_date: date
    end_date: date
    status: PhaseStatus
    progress: int | None = Field(description="100 once completed, else null = not available.")
    milestones: list[ClientMilestoneOut] = Field(description="Visible milestones, by due date.")


class ClientRoadmapOut(BaseModel):
    project_id: uuid.UUID
    today: date
    range_start: date | None
    range_end: date | None
    phases: list[ClientPhaseOut] = Field(description="Visible phases, in roadmap order.")
    unphased_milestones: list[ClientMilestoneOut] = Field(
        description="Visible milestones outside any visible phase, by due date."
    )


class ClientPortalOut(BaseModel):
    organisation: ClientOrganisationOut | None
    projects: list[ClientProjectOut]
    kpis: ClientKpis
    latest_report: ClientLatestReport | None
    upcoming_milestones: list[ClientUpcomingMilestone] = Field(
        description="Shared milestones not done yet, due today to 14 days ahead, by due date."
    )
    updates: list[ClientUpdateOut] = Field(description="Newest events first, at most 10.")
    summary: dict[str, int] = Field(
        description="Projects per health (on_track, at_risk, off_track, none) and `total`."
    )


class ClientCommentOut(BaseModel):
    """A message of the shared conversation (internal team notes never appear)."""

    id: uuid.UUID
    body: str
    author: str = Field(description="Name of the person who wrote it.")
    from_client: bool = Field(description="Written by a client contact (else by Borek).")
    created_at: datetime


class ClientAttachmentOut(BaseModel):
    id: uuid.UUID
    name: str
    content_type: str
    size_bytes: int
    uploaded_by: str = Field(description="Name of the person who added it.")
    created_at: datetime
