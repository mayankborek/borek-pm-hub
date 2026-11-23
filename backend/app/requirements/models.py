import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import sql_in
from app.core.database import Base, IdMixin, TimestampMixin


class RequirementStatus(StrEnum):
    """draft (never published) -> awaiting_acceptance (a version is with the client) ->
    accepted | rejected (final) or changes_requested (the PM publishes a new version)."""

    DRAFT = "draft"
    AWAITING_ACCEPTANCE = "awaiting_acceptance"
    CHANGES_REQUESTED = "changes_requested"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class AcceptanceDecision(StrEnum):
    """The client's answer to one published version."""

    ACCEPTED = "accepted"
    CHANGES_REQUESTED = "changes_requested"
    REJECTED = "rejected"


CLOSED = (RequirementStatus.ACCEPTED.value, RequirementStatus.REJECTED.value)


class Requirement(IdMixin, TimestampMixin, Base):
    """A requirement (deliverable) the client accepts. Its content lives in versions; the
    project lead or a Manager publishes a version for acceptance and the client answers that
    exact version. Accepted and rejected are final: later changes go through a change request."""

    __tablename__ = "requirements"
    __table_args__ = (
        UniqueConstraint("project_id", "code"),
        ForeignKeyConstraint(
            ["milestone_id", "project_id"],
            ["milestones.id", "milestones.project_id"],
            name="fk_requirements_milestone_id_milestones",
        ),
        CheckConstraint(sql_in("status", RequirementStatus), name="status"),
        Index("ix_requirements_project_id_status", "project_id", "status"),
        Index("ix_requirements_milestone_id", "milestone_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False)
    # REQ-01, REQ-02 ... per project, never reused.
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=RequirementStatus.DRAFT.value,
        server_default="draft",
    )
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}


class RequirementVersion(IdMixin, TimestampMixin, Base):
    """One version of a requirement's content. Only the newest version can be a draft; a
    published version never changes, and the client's answer is stored on it."""

    __tablename__ = "requirement_versions"
    __table_args__ = (
        UniqueConstraint("requirement_id", "number"),
        CheckConstraint("number >= 1", name="number_positive"),
        CheckConstraint(
            f"response IS NULL OR {sql_in('response', AcceptanceDecision)}", name="response"
        ),
        CheckConstraint("(response IS NULL) = (responded_at IS NULL)", name="responded_when_set"),
        CheckConstraint("response IS NULL OR published_at IS NOT NULL", name="answer_published"),
        CheckConstraint(
            "(published_at IS NULL) = (published_by IS NULL)", name="published_by_when_published"
        ),
    )

    requirement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("requirements.id"), nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    acceptance_criteria: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    change_note: Mapped[str | None] = mapped_column(Text)  # what changed since the last version
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    response: Mapped[str | None] = mapped_column(String(30))
    response_comment: Mapped[str | None] = mapped_column(Text)
    responded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
