"""organisation details + named client contacts per project (Administrator handoff 24.11.2026)

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("organisations", sa.Column("industry", sa.String(100), nullable=True))
    op.add_column("organisations", sa.Column("website", sa.String(300), nullable=True))
    op.add_column(
        "organisations", sa.Column("primary_contact_email", sa.String(320), nullable=True)
    )
    op.add_column("organisations", sa.Column("project_manager_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_organisations_project_manager_id_users"),
        "organisations",
        "users",
        ["project_manager_id"],
        ["id"],
    )

    op.create_table(
        "project_client_contacts",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_by", sa.Uuid(), nullable=True),
        sa.Column(
            "assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_client_contacts_project_id_projects"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_project_client_contacts_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by"],
            ["users.id"],
            name=op.f("fk_project_client_contacts_assigned_by_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_client_contacts")),
        sa.UniqueConstraint(
            "project_id", "user_id", name=op.f("uq_project_client_contacts_project_id_user_id")
        ),
    )
    op.create_index(
        "ix_project_client_contacts_user_id", "project_client_contacts", ["user_id"]
    )
    # Projects onboarded with a first contact (BB-13): that contact becomes the named contact
    # when they are the organisation's only client contact. Others show "needs assignment".
    op.execute(
        """
        INSERT INTO project_client_contacts (project_id, user_id)
        SELECT p.id, u.id
        FROM projects p
        JOIN users u ON u.organisation_id = p.client_organisation_id AND u.global_role = 'client'
        WHERE p.client_organisation_id IS NOT NULL
          AND (SELECT count(*) FROM users c
               WHERE c.organisation_id = p.client_organisation_id
                 AND c.global_role = 'client') = 1
        """
    )


def downgrade() -> None:
    op.drop_index("ix_project_client_contacts_user_id", table_name="project_client_contacts")
    op.drop_table("project_client_contacts")
    op.drop_constraint(
        op.f("fk_organisations_project_manager_id_users"), "organisations", type_="foreignkey"
    )
    op.drop_column("organisations", "project_manager_id")
    op.drop_column("organisations", "primary_contact_email")
    op.drop_column("organisations", "website")
    op.drop_column("organisations", "industry")
