"""project status 'cancelled'

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = "status IN ('planned', 'active', 'on_hold', 'completed')"
_NEW = "status IN ('planned', 'active', 'on_hold', 'completed', 'cancelled')"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_projects_status"), "projects", type_="check")
    op.create_check_constraint(op.f("ck_projects_status"), "projects", _NEW)


def downgrade() -> None:
    op.execute("UPDATE projects SET status = 'on_hold' WHERE status = 'cancelled'")
    op.drop_constraint(op.f("ck_projects_status"), "projects", type_="check")
    op.create_check_constraint(op.f("ck_projects_status"), "projects", _OLD)
