"""project money: one budget per project and dated entries (client payments, spending)

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_budgets",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="EUR", nullable=False),
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
        sa.CheckConstraint("amount >= 0", name=op.f("ck_project_budgets_amount_not_negative")),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_project_budgets_project_id_projects")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_budgets")),
        sa.UniqueConstraint("project_id", name=op.f("uq_project_budgets_project_id")),
    )
    op.create_table(
        "finance_entries",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint("amount > 0", name=op.f("ck_finance_entries_amount_positive")),
        sa.CheckConstraint("kind IN ('payment', 'spend')", name=op.f("ck_finance_entries_kind")),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_finance_entries_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_finance_entries_project_id_projects")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finance_entries")),
    )
    op.create_index(
        "ix_finance_entries_project_id_entry_date", "finance_entries", ["project_id", "entry_date"]
    )


def downgrade() -> None:
    op.drop_table("finance_entries")
    op.drop_table("project_budgets")
