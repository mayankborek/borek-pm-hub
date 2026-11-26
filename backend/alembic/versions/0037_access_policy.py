"""role permissions matrix + per-person project switches (Administrator handoff 10 + 11)

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _common() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("permission", sa.String(50), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "role_permission_settings",
        *_common(),
        sa.Column("role", sa.String(20), nullable=False),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name=op.f("fk_role_permission_settings_updated_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_role_permission_settings")),
        sa.UniqueConstraint(
            "role", "permission", name=op.f("uq_role_permission_settings_role_permission")
        ),
    )
    op.create_table(
        "project_permission_settings",
        *_common(),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_project_permission_settings_updated_by_users"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_permission_settings_project_id_projects"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_project_permission_settings_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_permission_settings")),
        sa.UniqueConstraint(
            "project_id",
            "user_id",
            "permission",
            name=op.f("uq_project_permission_settings_project_id_user_id_permission"),
        ),
    )
    op.create_index(
        "ix_project_permission_settings_user_id", "project_permission_settings", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_project_permission_settings_user_id", table_name="project_permission_settings")
    op.drop_table("project_permission_settings")
    op.drop_table("role_permission_settings")
