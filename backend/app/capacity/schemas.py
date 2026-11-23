import uuid
from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.validation import check_date, clean_optional_text

# Thresholds on the unrounded combined allocation (Manager Role Guide, Capacity 4).
CapacityStatus = Literal["available", "near_capacity", "overallocated", "unavailable", "conflict"]


def _days(values: list[int]) -> list[int]:
    days = sorted(set(values))
    if not days or any(d < 1 or d > 7 for d in days):
        raise ValueError("working_days are ISO weekdays 1 (Monday) to 7 (Sunday), at least one.")
    return days


class ScheduleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weekly_hours: float = Field(ge=0, le=168, description="Scheduled hours in a standard week.")
    working_days: list[int] = Field(description="ISO weekdays, 1 = Monday ... 7 = Sunday.")

    _clean_days = field_validator("working_days")(_days)


class ScheduleOut(BaseModel):
    weekly_hours: float
    working_days: list[int]
    hours_per_day: float = Field(description="weekly_hours spread evenly over working_days.")
    source: Literal["workspace", "personal"]


# --- reservations -------------------------------------------------------------------------------


def _date(value: date | None) -> date | None:
    return check_date(value, "date")


class ReservationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID = Field(description="An active member of the project.")
    start_date: date
    end_date: date = Field(description="Inclusive.")
    hours_per_week: float = Field(gt=0, le=168, description="Planned hours per standard week.")
    note: str | None = Field(default=None, max_length=1000)

    _clean_dates = field_validator("start_date", "end_date")(_date)

    @field_validator("note")
    @classmethod
    def _clean_note(cls, value: str | None) -> str | None:
        return clean_optional_text(value, max_length=1000, label="Note")

    @model_validator(mode="after")
    def _order(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date.")
        return self


class ReservationUpdate(BaseModel):
    """Send `version` plus only the fields that change."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    start_date: date | None = None
    end_date: date | None = None
    hours_per_week: float | None = Field(default=None, gt=0, le=168)
    note: str | None = Field(default=None, max_length=1000)

    _clean_dates = field_validator("start_date", "end_date")(_date)

    @field_validator("note")
    @classmethod
    def _clean_note(cls, value: str | None) -> str | None:
        return clean_optional_text(value, max_length=1000, label="Note")

    @model_validator(mode="after")
    def _required(self) -> Self:
        for name in ("start_date", "end_date", "hours_per_week"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} must not be null.")
        return self


class PersonRef(BaseModel):
    id: uuid.UUID
    name: str
    job_title: str | None


class ProjectRef(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class ReservationOut(BaseModel):
    id: uuid.UUID
    person: PersonRef
    project: ProjectRef
    start_date: date
    end_date: date
    hours_per_week: float
    note: str | None
    version: int


# --- capacity -----------------------------------------------------------------------------------


class ProjectShare(BaseModel):
    project: ProjectRef
    reserved_hours: float
    percent: float | None = Field(description="Of the available hours on the same dates.")


class Segment(BaseModel):
    """A stretch of dates where the person's bookings and availability stay the same: one piece
    of a timeline bar. Split where a project starts or stops."""

    start: date
    end: date
    available_hours: float
    reserved_hours: float
    total_percent: float | None = Field(
        description="Rounded to 2 decimals; the status uses the unrounded value. "
        "Null = nothing available."
    )
    capacity_left: float = Field(description="Negative = overallocated by that many hours.")
    status: CapacityStatus
    projects: list[ProjectShare]


class WeekOut(BaseModel):
    week_start: date = Field(description="Monday.")
    available_hours: float
    reserved_hours: float
    total_percent: float | None
    capacity_left: float
    status: CapacityStatus
    projects: list[ProjectShare]


class PersonCapacity(BaseModel):
    person: PersonRef
    schedule: ScheduleOut
    free_today: bool
    next_unallocated_day: date | None = Field(
        description="The next working day with nothing booked (looked up to one year ahead)."
    )
    free_until: date | None = Field(
        description="Last day of that free stretch before a known booking; null = open-ended."
    )
    has_engagements: bool = Field(description="Any booking intersecting the requested period.")
    segments: list[Segment] = Field(description="Bookings in the requested period, by date.")
    weeks: list[WeekOut]


class CapacitySummary(BaseModel):
    free_today: int = Field(description="People with working hours and nothing booked today.")
    free_within_3_months: int = Field(
        description="People free on at least one working day from today to 3 months later."
    )
    without_engagements: int = Field(description="People with no booking in the period.")


class CapacityOut(BaseModel):
    today: date
    timezone: str
    period_start: date
    period_end: date
    thresholds: dict[str, float] = Field(
        description="near_capacity from 80 %, overallocated above 100 %."
    )
    summary: CapacitySummary
    people: list[PersonCapacity]


# --- workload -----------------------------------------------------------------------------------


class WorkloadCounts(BaseModel):
    open: int = Field(description="Not done, in active projects.")
    overdue: int = Field(description="Open with a due date before today.")
    effort_pd: float | None = Field(
        description="Estimates of open tasks in person-days; null when none is estimated."
    )
    unestimated: int = Field(description="Open tasks without an estimate.")


class WorkloadProject(WorkloadCounts):
    project: ProjectRef
    client: str | None = Field(description="Client organisation name, if any.")


class WorkloadPerson(WorkloadCounts):
    person: PersonRef
    projects: list[WorkloadProject]


class WorkloadSummary(BaseModel):
    people_with_open_work: int
    projects_with_open_work: int
    open: int
    overdue: int
    effort_pd: float
    unestimated: int
    most_open: PersonRef | None
    most_open_count: int


class WorkloadOut(BaseModel):
    today: date
    hours_per_day: float = Field(description="Person-day length used (workspace schedule).")
    summary: WorkloadSummary
    people: list[WorkloadPerson] = Field(description="Highest remaining effort first.")
    unassigned: WorkloadCounts
    unassigned_projects: list[WorkloadProject]
