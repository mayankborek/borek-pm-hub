"""Project registers (BB-20, RD-10): risks, issues and decisions. One table, `kind` says which;
the fields that only fit one kind are null for the others (checked in the database)."""

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

from app.common.enums import TaskPriority
from app.core.database import Base, IdMixin, TimestampMixin


class RegisterKind(StrEnum):
    RISK = "risk"
    ISSUE = "issue"
    DECISION = "decision"


class Level(StrEnum):
    """Risk probability and impact."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskStatus(StrEnum):
    OPEN = "open"
    MITIGATING = "mitigating"
    CLOSED = "closed"


class IssueStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class DecisionStatus(StrEnum):
    PROPOSED = "proposed"
    DECIDED = "decided"
    SUPERSEDED = "superseded"


STATUSES: dict[RegisterKind, type[StrEnum]] = {
    RegisterKind.RISK: RiskStatus,
    RegisterKind.ISSUE: IssueStatus,
    RegisterKind.DECISION: DecisionStatus,
}
PREFIX = {RegisterKind.RISK: "R", RegisterKind.ISSUE: "I", RegisterKind.DECISION: "D"}


def _in(column: str, enum: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(repr(m.value) for m in enum)})"


class RegisterItem(IdMixin, TimestampMixin, Base):
    __tablename__ = "register_items"
    __table_args__ = (
        UniqueConstraint("project_id", "code"),
        CheckConstraint(_in("kind", RegisterKind), name="kind_valid"),
        CheckConstraint(
            " OR ".join(
                f"(kind = '{k.value}' AND {_in('status', s)})" for k, s in STATUSES.items()
            ),
            name="status_fits_kind",
        ),
        CheckConstraint(
            "kind = 'risk' OR (probability IS NULL AND impact IS NULL AND mitigation IS NULL)",
            name="risk_fields",
        ),
        CheckConstraint("kind = 'issue' OR priority IS NULL", name="issue_fields"),
        CheckConstraint(
            "kind = 'decision' OR (decided_on IS NULL AND decided_by IS NULL "
            "AND rationale IS NULL)",
            name="decision_fields",
        ),
        CheckConstraint(
            f"probability IS NULL OR {_in('probability', Level)}", name="probability_valid"
        ),
        CheckConstraint(f"impact IS NULL OR {_in('impact', Level)}", name="impact_valid"),
        CheckConstraint(
            f"priority IS NULL OR {_in('priority', TaskPriority)}", name="priority_valid"
        ),
        Index("ix_register_items_project_id_kind", "project_id", "kind"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    # R-01, I-01, D-01 ... per project and kind, never reused.
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    due_date: Mapped[date | None] = mapped_column(Date)
    # risks
    probability: Mapped[str | None] = mapped_column(String(10))
    impact: Mapped[str | None] = mapped_column(String(10))
    mitigation: Mapped[str | None] = mapped_column(Text)
    # issues (task priority scale)
    priority: Mapped[str | None] = mapped_column(String(20))
    # decisions
    decided_on: Mapped[date | None] = mapped_column(Date)
    decided_by: Mapped[str | None] = mapped_column(String(200))
    rationale: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}
