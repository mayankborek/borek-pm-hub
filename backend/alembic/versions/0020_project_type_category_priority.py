"""project type (internal/external), category and priority

Existing projects with a client organisation become external, all others internal.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TYPES = "project_type IN ('internal', 'external')"
_PRIORITIES = "priority IN ('highest', 'high', 'medium', 'low', 'lowest')"
_CLIENT = "(project_type = 'external') = (client_organisation_id IS NOT NULL)"


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("project_type", sa.String(length=20), nullable=False, server_default="internal"),
    )
    op.add_column("projects", sa.Column("category", sa.String(length=100), nullable=True))
    op.add_column(
        "projects",
        sa.Column("priority", sa.String(length=10), nullable=False, server_default="medium"),
    )
    op.execute(
        "UPDATE projects SET project_type = 'external' WHERE client_organisation_id IS NOT NULL"
    )
    op.create_check_constraint(op.f("ck_projects_project_type"), "projects", _TYPES)
    op.create_check_constraint(op.f("ck_projects_priority"), "projects", _PRIORITIES)
    op.create_check_constraint(op.f("ck_projects_client_matches_type"), "projects", _CLIENT)


def downgrade() -> None:
    op.drop_constraint(op.f("ck_projects_client_matches_type"), "projects", type_="check")
    op.drop_constraint(op.f("ck_projects_priority"), "projects", type_="check")
    op.drop_constraint(op.f("ck_projects_project_type"), "projects", type_="check")
    op.drop_column("projects", "priority")
    op.drop_column("projects", "category")
    op.drop_column("projects", "project_type")
