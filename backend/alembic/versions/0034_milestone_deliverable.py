"""milestone deliverable (PM design spec, Mayank 25.11.2026)

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("milestones", sa.Column("deliverable", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("milestones", "deliverable")
