import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
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
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import AttachmentKind, StatusCategory, TaskPriority, sql_in
from app.core.database import Base, IdMixin, TimestampMixin


class WorkflowStatus(IdMixin, TimestampMixin, Base):
    """A status a PM or project lead defined for one project (Jira-style, customizable)."""

    __tablename__ = "project_statuses"
    __table_args__ = (
        UniqueConstraint("project_id", "name"),
        # Lets tasks point at (status_id, project_id), so a task can never use another
        # project's status.
        UniqueConstraint("id", "project_id"),
        CheckConstraint(sql_in("category", StatusCategory), name="category"),
        Index("ix_project_statuses_project_id_position", "project_id", "position"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class Task(IdMixin, TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("project_id", "key"),
        ForeignKeyConstraint(
            ["status_id", "project_id"],
            ["project_statuses.id", "project_statuses.project_id"],
            name="fk_tasks_status_id_project_statuses",
        ),
        CheckConstraint(sql_in("priority", TaskPriority), name="priority"),
        CheckConstraint("progress BETWEEN 0 AND 100", name="progress_range"),
        CheckConstraint(
            "due_date IS NULL OR start_date IS NULL OR due_date >= start_date",
            name="dates_order",
        ),
        Index("ix_tasks_project_id_status_id", "project_id", "status_id"),
        Index("ix_tasks_assignee_id_status_id", "assignee_id", "status_id"),
        Index("ix_tasks_project_id_due_date", "project_id", "due_date"),
        Index("ix_tasks_project_id_updated_at", "project_id", "updated_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False)
    # <project code>-<n> (e.g. BFL-88), generated from projects.task_counter, never reused.
    key: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TaskPriority.MEDIUM.value, server_default="medium"
    )
    labels: Mapped[list[str]] = mapped_column(
        ARRAY(String(30)), nullable=False, default=list, server_default=text("'{}'")
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    # Also the "estimate" of the Figma designs: the date the task should be completed.
    due_date: Mapped[date | None] = mapped_column(Date)
    # Independent of status (F03, F08).
    progress: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    # Nullable: unassigned tasks are allowed. Membership is checked in the service layer.
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    # Required while the status is in the blocked category (service layer; the status lives in
    # another table so a CHECK constraint cannot see it).
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __mapper_args__ = {"version_id_col": version}


class TaskComment(IdMixin, TimestampMixin, Base):
    """A comment on a task (F08). Deleting archives it."""

    __tablename__ = "task_comments"
    __table_args__ = (Index("ix_task_comments_task_id_created_at", "task_id", "created_at"),)

    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tasks.id"), nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskAttachment(IdMixin, TimestampMixin, Base):
    """A file (stored by the app) or a link (URL only) attached to a task. Deleting archives it."""

    __tablename__ = "task_attachments"
    __table_args__ = (
        CheckConstraint(sql_in("kind", AttachmentKind), name="kind"),
        CheckConstraint(
            "(kind = 'link' AND url IS NOT NULL) OR (kind = 'file' AND storage_key IS NOT NULL)",
            name="kind_matches_fields",
        ),
        Index("ix_task_attachments_task_id_created_at", "task_id", "created_at"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tasks.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2000))
    storage_key: Mapped[str | None] = mapped_column(String(100))  # file name inside UPLOAD_DIR
    content_type: Mapped[str | None] = mapped_column(String(150))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskActivity(IdMixin, Base):
    """Who changed what and when (F08). Rows are only ever added."""

    __tablename__ = "task_activity"
    __table_args__ = (Index("ix_task_activity_task_id_created_at", "task_id", "created_at"),)

    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tasks.id"), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    # {"field": [old, new]} with readable values (status and assignee names, not ids).
    changes: Mapped[dict[str, list[object]]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
