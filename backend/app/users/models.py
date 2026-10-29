from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, text
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
    # Part of every access token; raising it (sign out, password reset) ends all older tokens.
    token_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.global_role})>"
