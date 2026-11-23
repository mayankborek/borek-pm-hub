import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, IdMixin


class Notification(IdMixin, Base):
    """One in-app notification for one person (fan-out on write). Written in the same
    transaction as the change that caused it. The frontend builds the text from `type` and
    `params` (English and German); `params` keeps a snapshot of the title, so renaming or
    archiving the item later does not break old notifications. Deleted after 90 days
    (scripts/cleanup_notifications.py): notifications are not business records."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_recipient_id_created_at", "recipient_id", "created_at"),
        Index(
            "ix_notifications_recipient_id_unread",
            "recipient_id",
            postgresql_where=text("read_at IS NULL"),
        ),
        Index("ix_notifications_created_at", "created_at"),
    )

    recipient_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. task.assigned
    # The setting it falls under (tasks_assigned, change_requests ...): why the person got it.
    setting: Mapped[str] = mapped_column(String(30), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("projects.id"))
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationSetting(Base):
    """A person's switched-off settings. No row = everything on (the defaults)."""

    __tablename__ = "notification_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), primary_key=True)
    muted: Mapped[list[str]] = mapped_column(
        ARRAY(String(30)), nullable=False, default=list, server_default=text("'{}'")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )
