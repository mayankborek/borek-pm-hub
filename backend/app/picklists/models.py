"""Picklists (BB-27): dropdown values the administrator can change. Workflow values (statuses,
priorities, roles ...) come from the code and are shown as protected lists; they cannot change
here because rules depend on them."""

import uuid
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Uuid, text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, IdMixin, TimestampMixin


class PicklistKey(StrEnum):
    """Lists the administrator edits."""

    PROJECT_CATEGORY = "project_category"
    COMMUNICATION_ROLE = "communication_role"  # stakeholders: how they are kept informed


class PicklistValue(IdMixin, TimestampMixin, Base):
    __tablename__ = "picklist_values"
    __table_args__ = (
        # One spelling per list, any letter case.
        Index("uq_picklist_values_list_key_value", "list_key", text("lower(value)"), unique=True),
        Index("ix_picklist_values_list_key_position", "list_key", "position"),
    )

    list_key: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[str] = mapped_column(String(100), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}
