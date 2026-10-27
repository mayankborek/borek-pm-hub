"""task priority: highest, high, medium, low, lowest (like Jira); critical becomes highest

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_tasks_priority"), "tasks", type_="check")
    op.execute("UPDATE tasks SET priority = 'highest' WHERE priority = 'critical'")
    op.create_check_constraint(
        op.f("ck_tasks_priority"),
        "tasks",
        "priority IN ('highest', 'high', 'medium', 'low', 'lowest')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_tasks_priority"), "tasks", type_="check")
    op.execute("UPDATE tasks SET priority = 'critical' WHERE priority = 'highest'")
    op.execute("UPDATE tasks SET priority = 'low' WHERE priority = 'lowest'")
    op.create_check_constraint(
        op.f("ck_tasks_priority"),
        "tasks",
        "priority IN ('critical', 'high', 'medium', 'low')",
    )
