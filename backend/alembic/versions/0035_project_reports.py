"""generated project reports (BB-21 / RD-11, report format = Figma prototype 25.11.2026)

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_reports",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("period_kind", sa.String(10), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "content",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prepared_by", sa.Uuid(), nullable=False),
        sa.Column(
            "shared_with",
            postgresql.ARRAY(sa.String(20)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("shared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shared_by", sa.Uuid(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint(
            "kind IN ('tasks', 'milestones', 'change_requests', 'project_status', 'other')",
            name=op.f("ck_project_reports_kind"),
        ),
        sa.CheckConstraint(
            "period_kind IN ('custom', 'weekly', 'overall')",
            name=op.f("ck_project_reports_period_kind"),
        ),
        sa.CheckConstraint(
            "(period_kind = 'custom' OR period_kind = 'weekly') = (period_start IS NOT NULL)",
            name=op.f("ck_project_reports_period_dates"),
        ),
        sa.CheckConstraint(
            "(period_start IS NULL) = (period_end IS NULL)",
            name=op.f("ck_project_reports_period_pair"),
        ),
        sa.CheckConstraint(
            "period_end IS NULL OR period_end >= period_start",
            name=op.f("ck_project_reports_period_order"),
        ),
        sa.CheckConstraint(
            "shared_with <@ ARRAY['account_manager', 'client', 'manager']::varchar[]",
            name=op.f("ck_project_reports_shared_with"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_project_reports_project_id_projects")
        ),
        sa.ForeignKeyConstraint(
            ["prepared_by"], ["users.id"], name=op.f("fk_project_reports_prepared_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["shared_by"], ["users.id"], name=op.f("fk_project_reports_shared_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_reports")),
    )
    op.create_index(
        "ix_project_reports_project_id_created_at",
        "project_reports",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_reports_project_id_created_at", table_name="project_reports")
    op.drop_table("project_reports")
