"""status_reports (RAG, draft/published, history) and the project stakeholder register

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "status_reports",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("rag", sa.String(length=10), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("achievements", sa.Text(), nullable=True),
        sa.Column("next_steps", sa.Text(), nullable=True),
        sa.Column("risks", sa.Text(), nullable=True),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("state", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("rag IN ('green', 'amber', 'red')", name=op.f("ck_status_reports_rag")),
        sa.CheckConstraint("state IN ('draft', 'published')", name=op.f("ck_status_reports_state")),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_status_reports_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_status_reports_project_id_projects")
        ),
        sa.ForeignKeyConstraint(
            ["published_by"], ["users.id"], name=op.f("fk_status_reports_published_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_status_reports")),
    )
    op.create_index(
        "ix_status_reports_project_id_report_date", "status_reports", ["project_id", "report_date"]
    )
    op.create_table(
        "stakeholders",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("organisation", sa.String(length=200), nullable=True),
        sa.Column("role_title", sa.String(length=200), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("influence", sa.String(length=10), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "influence IS NULL OR influence IN ('low', 'medium', 'high')",
            name=op.f("ck_stakeholders_influence"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_stakeholders_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_stakeholders_project_id_projects")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stakeholders")),
    )
    op.create_index(op.f("ix_stakeholders_project_id"), "stakeholders", ["project_id"])


def downgrade() -> None:
    op.drop_table("stakeholders")
    op.drop_table("status_reports")
