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
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import MembershipSource, ProjectRole, ProjectStatus, sql_in
from app.core.database import Base, IdMixin, TimestampMixin


class Project(IdMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(sql_in("status", ProjectStatus), name="status"),
        CheckConstraint(
            "target_end_date IS NULL OR start_date IS NULL OR target_end_date >= start_date",
            name="dates_order",
        ),
        CheckConstraint("task_counter >= 0", name="task_counter_non_negative"),
    )

    # Entered by the PM; must not change after creation (enforced in the service layer).
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ProjectStatus.PLANNED.value, server_default="planned"
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    target_end_date: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    # Last used TSK number; incremented atomically when a task is created.
    task_counter: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __mapper_args__ = {"version_id_col": version}


class ProjectMember(IdMixin, TimestampMixin, Base):
    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id"),
        CheckConstraint(sql_in("project_role", ProjectRole), name="project_role"),
        CheckConstraint(sql_in("source", MembershipSource), name="source"),
        Index("ix_project_members_user_id", "user_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    project_role: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ProjectRole.DEVELOPER.value, server_default="developer"
    )
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=MembershipSource.INVITATION.value,
        server_default="invitation",
    )
    granted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
