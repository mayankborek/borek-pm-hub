"""change requests, and the original due date of a milestone an approved request moved

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("milestones", sa.Column("original_due_date", sa.Date(), nullable=True))
    op.create_table(
        "change_requests",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("milestone_id", sa.Uuid(), nullable=True),
        sa.Column("requested_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("review_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("impact_schedule_days", sa.Integer(), nullable=True),
        sa.Column("impact_effort_hours", sa.Integer(), nullable=True),
        sa.Column("impact_scope", sa.Text(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_by", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'in_review', 'approved', 'declined')",
            name=op.f("ck_change_requests_status"),
        ),
        sa.CheckConstraint(
            "requested_date IS NULL OR milestone_id IS NOT NULL",
            name=op.f("ck_change_requests_date_needs_milestone"),
        ),
        sa.CheckConstraint(
            "impact_effort_hours IS NULL OR impact_effort_hours >= 0",
            name=op.f("ck_change_requests_effort_not_negative"),
        ),
        sa.CheckConstraint(
            "(status IN ('pending', 'in_review')) = (decided_at IS NULL)",
            name=op.f("ck_change_requests_decided_when_closed"),
        ),
        sa.CheckConstraint(
            "status = 'pending' OR review_started_at IS NOT NULL",
            name=op.f("ck_change_requests_reviewed_after_pending"),
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"], ["users.id"], name=op.f("fk_change_requests_decided_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["milestone_id", "project_id"],
            ["milestones.id", "milestones.project_id"],
            name="fk_change_requests_milestone_id_milestones",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_change_requests_project_id_projects")
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by"], ["users.id"], name=op.f("fk_change_requests_submitted_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_requests")),
        sa.UniqueConstraint("project_id", "code", name=op.f("uq_change_requests_project_id_code")),
    )
    op.create_index(
        "ix_change_requests_project_id_status", "change_requests", ["project_id", "status"]
    )
    op.create_index("ix_change_requests_milestone_id", "change_requests", ["milestone_id"])


def downgrade() -> None:
    op.drop_index("ix_change_requests_milestone_id", table_name="change_requests")
    op.drop_index("ix_change_requests_project_id_status", table_name="change_requests")
    op.drop_table("change_requests")
    op.drop_column("milestones", "original_due_date")
