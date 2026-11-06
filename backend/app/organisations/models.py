import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import OrganisationType, sql_in
from app.core.database import Base, IdMixin, TimestampMixin


class Organisation(IdMixin, TimestampMixin, Base):
    """Borek itself (internal) or a customer (client). Archived, never deleted."""

    __tablename__ = "organisations"
    __table_args__ = (
        CheckConstraint(sql_in("type", OrganisationType), name="type"),
        Index("uq_organisations_lower_name", text("lower(name)"), unique=True),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(
        String(20), nullable=False, default=OrganisationType.CLIENT.value, server_default="client"
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    __mapper_args__ = {"version_id_col": version}


class OrganisationAccountManager(IdMixin, Base):
    """An Account Manager follows the projects of the client organisations assigned here."""

    __tablename__ = "organisation_account_managers"
    __table_args__ = (
        UniqueConstraint("organisation_id", "user_id"),
        Index("ix_organisation_account_managers_user_id", "user_id"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organisations.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
