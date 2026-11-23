"""Team capacity inputs (Manager Role Guide, Capacity 2): working schedules and project
reservations. Reservations are planned hours per standard week, entered by a planner; they are
stored apart from tasks, so an estimate or a finished task never changes capacity."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, IdMixin, TimestampMixin

# ISO weekdays: 1 = Monday ... 7 = Sunday.
DEFAULT_WEEKLY_HOURS = Decimal("40")
DEFAULT_WORKING_DAYS = [1, 2, 3, 4, 5]


class WorkspaceSchedule(Base):
    """The workspace default working week (one row, id 1). Seeded with 40 h Monday-Friday."""

    __tablename__ = "workspace_schedule"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint("weekly_hours >= 0 AND weekly_hours <= 168", name="hours_range"),
        CheckConstraint("cardinality(working_days) >= 1", name="has_days"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    weekly_hours: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    working_days: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class UserSchedule(Base):
    """A person's own working week (part-time staff), instead of the workspace default."""

    __tablename__ = "user_schedules"
    __table_args__ = (
        CheckConstraint("weekly_hours >= 0 AND weekly_hours <= 168", name="hours_range"),
        CheckConstraint("cardinality(working_days) >= 1", name="has_days"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), primary_key=True)
    weekly_hours: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    working_days: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class Reservation(IdMixin, TimestampMixin, Base):
    """Planned hours per standard week for one person on one project, between two dates
    (both inclusive)."""

    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="dates_in_order"),
        CheckConstraint("hours_per_week > 0 AND hours_per_week <= 168", name="hours_range"),
        Index("ix_reservations_user_id_dates", "user_id", "start_date", "end_date"),
        Index("ix_reservations_project_id", "project_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    hours_per_week: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}


class MilestoneLateAlert(Base):
    """A "running late" notification was sent for this milestone and due date. A new due date
    (moved milestone) allows a new alert. Kept apart so the daily check never bumps the
    milestone's version."""

    __tablename__ = "milestone_late_alerts"

    milestone_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("milestones.id"), primary_key=True
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
