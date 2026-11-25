"""task reporter: who reported a task, editable by the PM (PM design spec 19.11.2026)

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("reporter_id", sa.Uuid(), nullable=True))
    op.execute("UPDATE tasks SET reporter_id = created_by")
    op.alter_column("tasks", "reporter_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_tasks_reporter_id_users"), "tasks", "users", ["reporter_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_tasks_reporter_id_users"), "tasks", type_="foreignkey")
    op.drop_column("tasks", "reporter_id")
