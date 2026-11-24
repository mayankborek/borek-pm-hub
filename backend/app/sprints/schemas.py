import uuid
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.validation import check_date, clean_optional_text, clean_text
from app.organisations.schemas import PersonBrief
from app.sprints.models import SprintState, TaskOutcome

MAX_GOAL = 2_000
MAX_MOVE = 200  # tasks per move request


def _name(value: str | None) -> str | None:
    return None if value is None else clean_text(value, label="Name")


def _goal(value: str | None) -> str | None:
    return clean_optional_text(value, max_length=MAX_GOAL, label="Goal", multiline=True)


def _date(value: date | None) -> date | None:
    return check_date(value, "date")


def _check_order(start: date | None, end: date | None) -> None:
    if start and end and end < start:
        raise ValueError("end_date must not be before start_date.")


class SprintCreate(BaseModel):
    """A new planned sprint. Without a name it is called "<project code> Sprint <number>"."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=200)
    goal: str | None = None
    start_date: date | None = None
    end_date: date | None = None

    _clean_name = field_validator("name")(_name)
    _clean_goal = field_validator("goal")(_goal)
    _clean_dates = field_validator("start_date", "end_date")(_date)

    @model_validator(mode="after")
    def _order(self) -> Self:
        _check_order(self.start_date, self.end_date)
        return self


class SprintUpdate(BaseModel):
    """Send `version` plus only the fields that change. Completed sprints cannot change. An
    active sprint keeps both dates (they cannot be cleared)."""

    model_config = ConfigDict(extra="forbid")

    version: int
    name: str | None = Field(default=None, max_length=200)
    goal: str | None = None
    start_date: date | None = None
    end_date: date | None = None

    _clean_name = field_validator("name")(_name)
    _clean_goal = field_validator("goal")(_goal)
    _clean_dates = field_validator("start_date", "end_date")(_date)

    @model_validator(mode="after")
    def _checks(self) -> Self:
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name must not be null.")
        _check_order(self.start_date, self.end_date)
        return self


class SprintStart(BaseModel):
    """Starts a planned sprint. Dates sent here replace the planned ones; both must be known."""

    model_config = ConfigDict(extra="forbid")

    version: int
    start_date: date | None = None
    end_date: date | None = None
    goal: str | None = None

    _clean_goal = field_validator("goal")(_goal)
    _clean_dates = field_validator("start_date", "end_date")(_date)

    @model_validator(mode="after")
    def _order(self) -> Self:
        _check_order(self.start_date, self.end_date)
        return self


class SprintComplete(BaseModel):
    """Completes the active sprint. Unfinished tasks go to `move_open_tasks_to` (a planned
    sprint of the project), to a new planned sprint (`create_next_sprint`), or else to the
    backlog."""

    model_config = ConfigDict(extra="forbid")

    version: int
    move_open_tasks_to: uuid.UUID | None = None
    create_next_sprint: bool = False

    @model_validator(mode="after")
    def _one_target(self) -> Self:
        if self.move_open_tasks_to and self.create_next_sprint:
            raise ValueError("Send move_open_tasks_to or create_next_sprint, not both.")
        return self


class MoveTasks(BaseModel):
    """Puts tasks into a planned or active sprint, or back into the backlog (`sprint_id`
    null)."""

    model_config = ConfigDict(extra="forbid")

    task_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_MOVE)
    sprint_id: uuid.UUID | None


class SprintBrief(BaseModel):
    id: uuid.UUID
    number: int
    name: str
    state: SprintState


class SprintCounts(BaseModel):
    """Current tasks in the sprint (archived tasks not counted)."""

    total: int
    done: int
    open: int


class SprintReport(BaseModel):
    """What happened when the sprint was completed (completed sprints only)."""

    committed: int | None = Field(description="Tasks in the sprint when it was started.")
    completed: int
    spilled: int
    spilled_to: SprintBrief | None = Field(description="Null: unfinished tasks went to backlog.")


class SprintOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    number: int
    name: str
    goal: str | None
    start_date: date | None
    end_date: date | None
    state: SprintState
    today: date
    days_left: int | None = Field(description="Active sprints: days to end_date (negative = over).")
    counts: SprintCounts
    report: SprintReport | None
    started_at: datetime | None
    started_by: PersonBrief | None
    completed_at: datetime | None
    completed_by: PersonBrief | None
    created_at: datetime
    version: int


class SprintListOut(BaseModel):
    items: list[SprintOut]
    total: int
    page: int
    page_size: int


class SprintTaskOut(BaseModel):
    """A task in the sprint now (planned/active), or as recorded on completion (completed)."""

    id: uuid.UUID
    key: str
    title: str
    status_name: str
    status_category: str | None = Field(description="Now; null for a recorded outcome.")
    assignee: PersonBrief | None
    outcome: TaskOutcome | None = Field(description="Completed sprints: done or spilled.")
    moved_to: SprintBrief | None = Field(description="Spilled tasks: the sprint they went to.")
    times_spilled: int = Field(description="In how many completed sprints it was not finished.")


class SprintDetailOut(SprintOut):
    tasks: list[SprintTaskOut]


class MoveTasksOut(BaseModel):
    moved: int
