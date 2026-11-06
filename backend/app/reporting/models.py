import uuid
from datetime import date, datetime

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
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import RagStatus, ReportState, StakeholderInfluence, sql_in
from app.core.database import Base, IdMixin, TimestampMixin


class StatusReport(IdMixin, TimestampMixin, Base):
    """A dated project status. Drafts can change; a published report is history and stays as is.
    The newest published report is the project's current RAG."""

    __tablename__ = "status_reports"
    __table_args__ = (
        CheckConstraint(sql_in("rag", RagStatus), name="rag"),
        CheckConstraint(sql_in("state", ReportState), name="state"),
        Index("ix_status_reports_project_id_report_date", "project_id", "report_date"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False)
    rag: Mapped[str] = mapped_column(String(10), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    achievements: Mapped[str | None] = mapped_column(Text)
    next_steps: Mapped[str | None] = mapped_column(Text)
    risks: Mapped[str | None] = mapped_column(Text)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ReportState.DRAFT.value, server_default="draft"
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}


class Stakeholder(IdMixin, TimestampMixin, Base):
    """Someone with an interest in the project, usually without an account."""

    __tablename__ = "stakeholders"
    __table_args__ = (
        CheckConstraint(
            f"influence IS NULL OR {sql_in('influence', StakeholderInfluence)}", name="influence"
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    organisation: Mapped[str | None] = mapped_column(String(200))
    role_title: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    influence: Mapped[str | None] = mapped_column(String(10))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}
