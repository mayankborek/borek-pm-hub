"""admin accounts: more roles, users.join_date, user_invites

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = "global_role IN ('pm', 'developer')"
_NEW = "global_role IN ('admin', 'pm', 'developer', 'manager', 'account_manager', 'client')"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_users_global_role"), "users", type_="check")
    op.create_check_constraint(op.f("ck_users_global_role"), "users", _NEW)
    op.add_column("users", sa.Column("join_date", sa.Date(), nullable=True))
    op.create_table(
        "user_invites",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_user_invites_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_invites_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_invites")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_invites_token_hash")),
    )
    op.create_index(op.f("ix_user_invites_user_id"), "user_invites", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_invites_user_id"), table_name="user_invites")
    op.drop_table("user_invites")
    op.drop_column("users", "join_date")
    # Accounts with a role the old rule does not know cannot stay: they become developers.
    op.execute(
        "UPDATE users SET global_role = 'developer' WHERE global_role NOT IN ('pm', 'developer')"
    )
    op.drop_constraint(op.f("ck_users_global_role"), "users", type_="check")
    op.create_check_constraint(op.f("ck_users_global_role"), "users", _OLD)
