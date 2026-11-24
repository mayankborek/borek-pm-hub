"""Sprints (Jira-like): a time box per project. Planned -> active -> completed; one active sprint
per project at a time. A task is in at most one sprint (`tasks.sprint_id`); without one it is in
the backlog. Completing a sprint records what happened to every task in it (the sprint history
and the spillover), because the tasks move on afterwards."""

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, IdMixin, TimestampMixin


class SprintState(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"


class TaskOutcome(StrEnum):
    DONE = "done"  # in a done status when the sprint was completed
    SPILLED = "spilled"  # not done: moved to another sprint or the backlog


class Sprint(IdMixin, TimestampMixin, Base):
    __tablename__ = "sprints"
    __table_args__ = (
        UniqueConstraint("project_id", "number"),
        # Lets tasks point at (sprint_id, project_id): never at another project's sprint.
        UniqueConstraint("id", "project_id"),
        CheckConstraint("state IN ('planned', 'active', 'completed')", name="state_valid"),
        CheckConstraint("end_date >= start_date", name="dates_order"),
        CheckConstraint(
            "state = 'planned' OR (start_date IS NOT NULL AND end_date IS NOT NULL)",
            name="dates_when_started",
        ),
        CheckConstraint("(started_at IS NULL) = (state = 'planned')", name="started_pair"),
        CheckConstraint("(completed_at IS NULL) = (state <> 'completed')", name="completed_pair"),
        # One active sprint per project.
        Index(
            "uq_sprints_one_active_per_project",
            "project_id",
            unique=True,
            postgresql_where=text("state = 'active'"),
        ),
        Index("ix_sprints_project_id_state", "project_id", "state"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False)
    # 1, 2, 3 ... per project, never reused (archived ones keep theirs).
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    goal: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SprintState.PLANNED.value, server_default="planned"
    )
    # Tasks in the sprint when it was started (the commitment).
    committed_count: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    # Where the unfinished tasks went on completion; null = the backlog.
    spilled_to_sprint_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("sprints.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}


class SprintTaskOutcome(Base):
    """One row per task that was in a sprint when it was completed: the sprint report."""

    __tablename__ = "sprint_task_outcomes"
    __table_args__ = (
        CheckConstraint("outcome IN ('done', 'spilled')", name="outcome_valid"),
        Index("ix_sprint_task_outcomes_task_id", "task_id"),
    )

    sprint_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sprints.id", ondelete="CASCADE"), primary_key=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    # The status the task had at that moment (readable after statuses are renamed or deleted).
    status_name: Mapped[str] = mapped_column(String(50), nullable=False)
    moved_to_sprint_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("sprints.id"))
