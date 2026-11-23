import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.milestones.schemas import MilestoneState


class NextMilestone(BaseModel):
    """The open milestone due first (late ones included, so a missed date is not hidden)."""

    id: uuid.UUID
    code: str
    name: str
    due_date: date
    state: MilestoneState


class PublishedProgress(BaseModel):
    """Progress the PM shared in the newest published report that has a figure."""

    percent: int
    published_on: date = Field(description="Date of that report.")
    published_by: str | None = Field(description="Name of the person who published it.")
    report_id: uuid.UUID


class ProjectRef(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class DeliveryEvent(BaseModel):
    """For "Recent updates" (dashboard) and "Recent activity" (project overview)."""

    kind: Literal["report", "change_request", "milestone", "requirement"]
    project: ProjectRef
    title: str = Field(description="Report title, or the code and title of the item.")
    occurred_at: datetime
    entity_id: uuid.UUID
    status: str | None = Field(
        description="report: null; change_request: the status this event set (pending = raised);"
        ' milestone: shared (shared with the client: "Milestone schedule published") or done;'
        " requirement: awaiting_acceptance (published) or the client's answer."
    )
    due_date: date | None = Field(default=None, description="For kind milestone.")


class UpcomingMilestone(NextMilestone):
    project: ProjectRef


class ManagerKpis(BaseModel):
    active_projects: int = Field(description="Not completed, not cancelled.")
    shared_reports: int = Field(description="Published status reports.")
    upcoming_milestones: int = Field(description="Open milestones due in the next 14 days.")
    requests_in_review: int = Field(description="Change requests in review.")
    requests_pending: int = Field(description="Change requests raised, review not started.")
    awaiting_client: int = Field(description="Requirements waiting for the client's answer.")


class ManagerDashboardOut(BaseModel):
    today: date
    kpis: ManagerKpis
    upcoming_milestones: list[UpcomingMilestone] = Field(description="Next 14 days, by date.")
    updates: list[DeliveryEvent] = Field(description="Newest first, at most 10.")


class MilestoneCompletion(BaseModel):
    done: int
    total: int


class TrendPoint(BaseModel):
    report_id: uuid.UUID
    report_date: date
    percent: int


class ProjectOverviewOut(BaseModel):
    """The delivery summary of one project (Manager, Account Manager and the project team)."""

    project: ProjectRef
    today: date
    target_end_date: date | None
    days_left: int | None = Field(description="Until the target end date; negative = overdue.")
    progress: PublishedProgress | None = Field(description="Null = not published yet.")
    progress_trend: list[TrendPoint] = Field(description="Published progress per report, oldest.")
    milestones: MilestoneCompletion
    next_milestone: NextMilestone | None
    client_actions: int = Field(description="Requirements waiting for the client's answer.")
    activity: list[DeliveryEvent] = Field(description="Newest first, at most 10.")
