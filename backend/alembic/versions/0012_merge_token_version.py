"""merge the security branch migration (0009) with the admin accounts line (0011)

0009 was written on fix/PT-38-security-hardening, while dev went 0008 -> 0010 -> 0011. A database
already at 0011 gets 0009 from this merge, and merging that branch later adds no second head.

Revision ID: 0012
Revises: 0009, 0011
Create Date: 2026-11-06
"""

from collections.abc import Sequence

revision: str = "0012"
down_revision: str | Sequence[str] | None = ("0009", "0011")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
