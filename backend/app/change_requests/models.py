import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
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

from app.common.enums import ImpactUnit, sql_in
from app.core.database import Base, IdMixin, TimestampMixin


class ChangeRequestStatus(StrEnum):
    """pending (just raised) -> in_review (the lead started the review) -> approved | declined.
    The frontend labels approved as "Accepted"."""

    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    DECLINED = "declined"


class ChangeRequest(IdMixin, TimestampMixin, Base):
    """A request to change scope or dates. Anyone working with the project (client included)
    raises one; the project lead or a Manager fills in the impact and decides.

    With a milestone and a requested date, approving it moves the milestone to that date (the
    milestone then shows as "revised")."""

    __tablename__ = "change_requests"
    __table_args__ = (
        UniqueConstraint("project_id", "code"),
        ForeignKeyConstraint(
            ["milestone_id", "project_id"],
            ["milestones.id", "milestones.project_id"],
            name="fk_change_requests_milestone_id_milestones",
        ),
        CheckConstraint(sql_in("status", ChangeRequestStatus), name="status"),
        CheckConstraint(
            "requested_date IS NULL OR milestone_id IS NOT NULL", name="date_needs_milestone"
        ),
        CheckConstraint(sql_in("impact_schedule_unit", ImpactUnit), name="impact_schedule_unit"),
        CheckConstraint(sql_in("impact_effort_unit", ImpactUnit), name="impact_effort_unit"),
        CheckConstraint(
            "(impact_schedule_value IS NULL) = (impact_schedule_unit IS NULL)",
            name="impact_schedule_pair",
        ),
        CheckConstraint(
            "(impact_effort_value IS NULL) = (impact_effort_unit IS NULL)",
            name="impact_effort_pair",
        ),
        CheckConstraint(
            "impact_effort_value IS NULL OR impact_effort_value >= 0", name="effort_not_negative"
        ),
        CheckConstraint(
            "(status IN ('pending', 'in_review')) = (decided_at IS NULL)",
            name="decided_when_closed",
        ),
        CheckConstraint(
            "status = 'pending' OR review_started_at IS NOT NULL", name="reviewed_after_pending"
        ),
        Index("ix_change_requests_project_id_status", "project_id", "status"),
        Index("ix_change_requests_milestone_id", "milestone_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False)
    # CR-01, CR-02 ... per project, never reused.
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    requested_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ChangeRequestStatus.PENDING.value,
        server_default="pending",
    )
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Impact, filled in by the project lead or a Manager.
    # Each impact is an amount plus a unit (hours, days, weeks); both set or both null.
    # Schedule: how far the delivery moves (minus = earlier). Effort: extra work.
    impact_schedule_value: Mapped[int | None] = mapped_column(Integer)
    impact_schedule_unit: Mapped[str | None] = mapped_column(String(10))
    impact_effort_value: Mapped[int | None] = mapped_column(Integer)
    impact_effort_unit: Mapped[str | None] = mapped_column(String(10))
    impact_scope: Mapped[str | None] = mapped_column(Text)
    decision_note: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}


class ChangeRequestComment(IdMixin, TimestampMixin, Base):
    """A message on a change request. Shared ones are the conversation with the client;
    internal ones are notes for the project team only and never reach the client."""

    __tablename__ = "change_request_comments"
    __table_args__ = (
        Index(
            "ix_change_request_comments_request_id_created_at", "change_request_id", "created_at"
        ),
    )

    change_request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("change_requests.id"), nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    internal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )


class ChangeRequestAttachment(IdMixin, TimestampMixin, Base):
    """A file attached to a change request; shown to everyone who sees the request."""

    __tablename__ = "change_request_attachments"
    __table_args__ = (
        Index(
            "ix_change_request_attachments_request_id_created_at",
            "change_request_id",
            "created_at",
        ),
    )

    change_request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("change_requests.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(100), nullable=False)
    content_type: Mapped[str] = mapped_column(String(150), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
