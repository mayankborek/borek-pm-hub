"""tasks.external_key: the key a task had in the system it was imported from (e.g. Jira)

Revision ID: 0010
Revises: 0008
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "uq_tasks_project_id_external_key"


def upgrade() -> None:
    op.add_column("tasks", sa.Column("external_key", sa.String(length=50), nullable=True))
    # Re-importing the same file must not create the task twice. Only tasks that came from an
    # import have a value, so the rule applies to those alone.
    op.create_index(
        _INDEX,
        "tasks",
        ["project_id", "external_key"],
        unique=True,
        postgresql_where=sa.text("external_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="tasks")
    op.drop_column("tasks", "external_key")
