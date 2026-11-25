"""Generated project reports (BB-21 / RD-11, report format = Mayank's Figma prototype 25.11.2026).

A report is generated from the project's data for a type and a reporting period, kept as a
snapshot (`content`) so it never changes after it was shared, previewed, downloaded as PDF and
shared inside the app with the Account Manager, the client portal and/or the Managers. Separate
from the hand-written status reports (app/reporting)."""

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import sql_in
from app.core.database import Base, IdMixin, TimestampMixin


class ReportKind(StrEnum):
    TASKS = "tasks"
    MILESTONES = "milestones"
    CHANGE_REQUESTS = "change_requests"
    PROJECT_STATUS = "project_status"
    OTHER = "other"


class PeriodKind(StrEnum):
    CUSTOM = "custom"  # start and end date
    WEEKLY = "weekly"  # Monday to Sunday
    OVERALL = "overall"  # the whole project, no dates


class Audience(StrEnum):
    ACCOUNT_MANAGER = "account_manager"
    CLIENT = "client"
    MANAGER = "manager"


class ProjectReport(IdMixin, TimestampMixin, Base):
    __tablename__ = "project_reports"
    __table_args__ = (
        CheckConstraint(sql_in("kind", ReportKind), name="kind"),
        CheckConstraint(sql_in("period_kind", PeriodKind), name="period_kind"),
        CheckConstraint(
            "(period_kind = 'custom' OR period_kind = 'weekly') = (period_start IS NOT NULL)",
            name="period_dates",
        ),
        CheckConstraint("(period_start IS NULL) = (period_end IS NULL)", name="period_pair"),
        CheckConstraint("period_end IS NULL OR period_end >= period_start", name="period_order"),
        CheckConstraint(
            "shared_with <@ ARRAY['account_manager', 'client', 'manager']::varchar[]",
            name="shared_with",
        ),
        Index("ix_project_reports_project_id_created_at", "project_id", "created_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    period_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    # The "expert summary": the PM's own analysis (required for kind other, optional otherwise).
    summary: Mapped[str | None] = mapped_column(Text)
    # The figures and tables as generated (see schemas.ReportContent). Never recomputed.
    content: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    prepared_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    shared_with: Mapped[list[str]] = mapped_column(
        ARRAY(String(20)), nullable=False, default=list, server_default=text("'{}'")
    )
    shared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shared_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}
