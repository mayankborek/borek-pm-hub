"""Project roadmap: phases (a stretch of time, drawn as a bar) and milestones (a due date, drawn
as a diamond). Status, state and progress are never stored; they are worked out when read
(`app.milestones.service`), so they cannot go stale."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, IdMixin, TimestampMixin


class ProjectPhase(IdMixin, TimestampMixin, Base):
    """A part of the project with a start and an end, e.g. Design or Testing."""

    __tablename__ = "project_phases"
    __table_args__ = (
        # Lets milestones point at (phase_id, project_id): never at another project's phase.
        UniqueConstraint("id", "project_id"),
        CheckConstraint("end_date >= start_date", name="dates_order"),
        Index("ix_project_phases_project_id_position", "project_id", "position"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    client_visible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}


class Milestone(IdMixin, TimestampMixin, Base):
    """A delivery point with a due date, e.g. "Design approved". Optionally inside a phase.
    Tasks link to it (`tasks.milestone_id`); its progress is the share of those that are done."""

    __tablename__ = "milestones"
    __table_args__ = (
        UniqueConstraint("project_id", "code"),
        # Lets tasks point at (milestone_id, project_id): never at another project's milestone.
        UniqueConstraint("id", "project_id"),
        ForeignKeyConstraint(
            ["phase_id", "project_id"],
            ["project_phases.id", "project_phases.project_id"],
            name="fk_milestones_phase_id_project_phases",
        ),
        CheckConstraint("(completed_at IS NULL) = (completed_by IS NULL)", name="completed_pair"),
        Index("ix_milestones_project_id_due_date", "project_id", "due_date"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False)
    phase_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    # M-01, M-02 ... per project, never reused (archived ones keep theirs).
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    completion_criteria: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    # Set by the PM when the milestone is reached ("Milestone reached" on the roadmap).
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    # The PM's warning; a passed due date makes it "late" without any flag.
    at_risk: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    client_visible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}
