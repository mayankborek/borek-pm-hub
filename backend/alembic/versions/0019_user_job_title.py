"""user job title: optional free text set by the administrator

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("job_title", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "job_title")
