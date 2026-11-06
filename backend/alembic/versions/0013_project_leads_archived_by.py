"""projects.archived_by; every project's creator (PM or Manager) becomes its project lead

Needed before PMs are limited to their own projects: without this a PM would lose the projects
they created. Other PMs keep whatever membership they already have.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("archived_by", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_projects_archived_by_users"), "projects", "users", ["archived_by"], ["id"]
    )
    op.execute(
        """
        UPDATE project_members m
        SET project_role = 'project_lead'
        FROM projects p
        JOIN users u ON u.id = p.created_by
        WHERE m.project_id = p.id
          AND m.user_id = p.created_by
          AND m.project_role <> 'project_lead'
          AND u.global_role IN ('pm', 'manager')
        """
    )
    op.execute(
        """
        INSERT INTO project_members (project_id, user_id, project_role, source, granted_by)
        SELECT p.id, p.created_by, 'project_lead', 'invitation', p.created_by
        FROM projects p
        JOIN users u ON u.id = p.created_by
        WHERE u.global_role IN ('pm', 'manager')
          AND NOT EXISTS (
            SELECT 1 FROM project_members m
            WHERE m.project_id = p.id AND m.user_id = p.created_by
          )
        """
    )


def downgrade() -> None:
    # The memberships stay: they are valid data under the old rules too.
    op.drop_constraint(op.f("fk_projects_archived_by_users"), "projects", type_="foreignkey")
    op.drop_column("projects", "archived_by")
