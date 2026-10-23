"""task estimate (free text, e.g. "5 points")

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("estimate", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "estimate")
