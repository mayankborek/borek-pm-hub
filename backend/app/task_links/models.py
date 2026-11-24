"""Links between tasks of one project (Jira-like): blocks, relates to, duplicates, clones.

One row per link, stored in its "active" direction (A blocks B). Each task shows it from its own
side ("blocks" on A, "is blocked by" on B). "Relates to" has no direction and is stored once."""

import uuid
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, IdMixin, TimestampMixin


class LinkType(StrEnum):
    BLOCKS = "blocks"
    RELATES_TO = "relates_to"
    DUPLICATES = "duplicates"
    CLONES = "clones"


class TaskLink(IdMixin, TimestampMixin, Base):
    __tablename__ = "task_links"
    __table_args__ = (
        UniqueConstraint("source_task_id", "target_task_id", "link_type"),
        CheckConstraint("source_task_id <> target_task_id", name="not_self"),
        CheckConstraint(
            "link_type IN ('blocks', 'relates_to', 'duplicates', 'clones')", name="type_valid"
        ),
        Index("ix_task_links_target_task_id", "target_task_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False)
    source_task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    target_task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    link_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
