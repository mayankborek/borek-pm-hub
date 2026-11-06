"""organisations; users and projects link to one; account managers assigned to client organisations

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organisations",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("type", sa.String(length=20), server_default="client", nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("type IN ('internal', 'client')", name=op.f("ck_organisations_type")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organisations")),
    )
    op.create_index(
        "uq_organisations_lower_name", "organisations", [sa.text("lower(name)")], unique=True
    )

    op.add_column("users", sa.Column("organisation_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_users_organisation_id_organisations"),
        "users",
        "organisations",
        ["organisation_id"],
        ["id"],
    )
    op.create_index(op.f("ix_users_organisation_id"), "users", ["organisation_id"])

    op.add_column("projects", sa.Column("client_organisation_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_projects_client_organisation_id_organisations"),
        "projects",
        "organisations",
        ["client_organisation_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_projects_client_organisation_id"), "projects", ["client_organisation_id"]
    )

    op.create_table(
        "organisation_account_managers",
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("granted_by", sa.Uuid(), nullable=True),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["granted_by"],
            ["users.id"],
            name=op.f("fk_organisation_account_managers_granted_by_users"),
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_organisation_account_managers_organisation_id_organisations"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_organisation_account_managers_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organisation_account_managers")),
        sa.UniqueConstraint(
            "organisation_id",
            "user_id",
            name=op.f("uq_organisation_account_managers_organisation_id_user_id"),
        ),
    )
    op.create_index(
        "ix_organisation_account_managers_user_id", "organisation_account_managers", ["user_id"]
    )

    # Everyone who exists today works for Borek; projects get their client later, by hand.
    op.execute(
        "INSERT INTO organisations (name, type) VALUES ('Borek Solutions Group', 'internal')"
    )
    op.execute(
        """
        UPDATE users SET organisation_id =
            (SELECT id FROM organisations WHERE name = 'Borek Solutions Group')
        """
    )


def downgrade() -> None:
    op.drop_table("organisation_account_managers")
    op.drop_index(op.f("ix_projects_client_organisation_id"), table_name="projects")
    op.drop_constraint(
        op.f("fk_projects_client_organisation_id_organisations"), "projects", type_="foreignkey"
    )
    op.drop_column("projects", "client_organisation_id")
    op.drop_index(op.f("ix_users_organisation_id"), table_name="users")
    op.drop_constraint(op.f("fk_users_organisation_id_organisations"), "users", type_="foreignkey")
    op.drop_column("users", "organisation_id")
    op.drop_table("organisations")
