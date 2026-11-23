"""milestones.shared_at: when a milestone was shared with the client ("Milestone schedule
published" in Recent updates). Milestones shared already get their creation time.

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("milestones", sa.Column("shared_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE milestones SET shared_at = created_at WHERE client_visible")


def downgrade() -> None:
    op.drop_column("milestones", "shared_at")
