"""Administrator settings on top of the built-in rights (Administrator handoff 10 + 11).

Only changes from the defaults are stored: resetting deletes rows. The defaults live in code
(`app.auth.policy`), so a release can change them without a data migration.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, IdMixin


class RolePermissionSetting(IdMixin, Base):
    """A role matrix cell switched by an administrator (screen 11)."""

    __tablename__ = "role_permission_settings"
    __table_args__ = (UniqueConstraint("role", "permission"),)

    role: Mapped[str] = mapped_column(String(20), nullable=False)
    permission: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class ProjectPermissionSetting(IdMixin, Base):
    """One person's switch in one project (screen 10)."""

    __tablename__ = "project_permission_settings"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", "permission"),
        Index("ix_project_permission_settings_user_id", "user_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    permission: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
