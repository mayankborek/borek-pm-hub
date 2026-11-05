import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import GlobalRole, sql_in
from app.core.database import Base, IdMixin, TimestampMixin


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(sql_in("global_role", GlobalRole), name="global_role"),)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    global_role: Mapped[str] = mapped_column(String(20), nullable=False)
    # Empty now; will hold the Entra object ID when AUTH_MODE=entra.
    external_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    # Argon2 hash for AUTH_MODE=local; None for accounts that sign in through Entra.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    failed_login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # Optional: the day the person joined (set by the administrator).
    join_date: Mapped[date | None] = mapped_column(Date)

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.global_role})>"


class UserInvite(IdMixin, Base):
    """A one-use link that lets a person set their own password (also used to reset it).

    Only a hash of the token is stored, so a copy of the database cannot be used to sign in.
    """

    __tablename__ = "user_invites"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    # SHA-256 (hex) of the token. The token is random and long, so a fast hash is enough.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when the administrator makes a newer link (the older one stops working).
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
