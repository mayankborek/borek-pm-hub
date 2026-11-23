"""in-app notifications and per-person notification settings

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("setting", sa.String(length=30), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_notifications_actor_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_notifications_project_id_projects")
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"], ["users.id"], name=op.f("fk_notifications_recipient_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(
        "ix_notifications_recipient_id_created_at", "notifications", ["recipient_id", "created_at"]
    )
    op.create_index(
        "ix_notifications_recipient_id_unread",
        "notifications",
        ["recipient_id"],
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])

    op.create_table(
        "notification_settings",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "muted",
            postgresql.ARRAY(sa.String(length=30)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_notification_settings_user_id_users")
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_notification_settings")),
    )


def downgrade() -> None:
    op.drop_table("notification_settings")
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_recipient_id_unread", table_name="notifications")
    op.drop_index("ix_notifications_recipient_id_created_at", table_name="notifications")
    op.drop_table("notifications")
