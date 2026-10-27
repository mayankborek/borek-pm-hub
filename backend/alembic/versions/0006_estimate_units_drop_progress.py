"""task estimate as amount + unit (minutes, hours, weeks); drop progress (PT-23)

Old free-text estimates ("5 points") are dropped on purpose, as decided for PT-23.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_tasks_progress_range"), "tasks", type_="check")
    op.drop_column("tasks", "progress")
    op.drop_column("tasks", "estimate")
    op.add_column("tasks", sa.Column("estimate_value", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("estimate_unit", sa.String(length=10), nullable=True))
    op.create_check_constraint(
        op.f("ck_tasks_estimate_unit"),
        "tasks",
        "estimate_unit IN ('minutes', 'hours', 'weeks')",
    )
    op.create_check_constraint(
        op.f("ck_tasks_estimate_positive"), "tasks", "estimate_value IS NULL OR estimate_value > 0"
    )
    op.create_check_constraint(
        op.f("ck_tasks_estimate_pair"),
        "tasks",
        "(estimate_value IS NULL) = (estimate_unit IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_tasks_estimate_pair"), "tasks", type_="check")
    op.drop_constraint(op.f("ck_tasks_estimate_positive"), "tasks", type_="check")
    op.drop_constraint(op.f("ck_tasks_estimate_unit"), "tasks", type_="check")
    op.drop_column("tasks", "estimate_unit")
    op.drop_column("tasks", "estimate_value")
    op.add_column("tasks", sa.Column("estimate", sa.String(length=50), nullable=True))
    op.add_column(
        "tasks",
        sa.Column("progress", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_tasks_progress_range"), "tasks", "progress BETWEEN 0 AND 100"
    )
