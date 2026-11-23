"""team capacity: workspace schedule (seeded 40 h Mon-Fri), personal schedules, project
reservations; milestone late alerts

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _now(name: str) -> sa.Column[object]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "workspace_schedule",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("weekly_hours", sa.Numeric(5, 2), nullable=False),
        sa.Column("working_days", postgresql.ARRAY(sa.Integer()), nullable=False),
        _now("updated_at"),
        sa.CheckConstraint("id = 1", name=op.f("ck_workspace_schedule_single_row")),
        sa.CheckConstraint(
            "weekly_hours >= 0 AND weekly_hours <= 168",
            name=op.f("ck_workspace_schedule_hours_range"),
        ),
        sa.CheckConstraint(
            "cardinality(working_days) >= 1", name=op.f("ck_workspace_schedule_has_days")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace_schedule")),
    )
    op.execute(
        "INSERT INTO workspace_schedule (id, weekly_hours, working_days) "
        "VALUES (1, 40, '{1,2,3,4,5}')"
    )
    op.create_table(
        "user_schedules",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("weekly_hours", sa.Numeric(5, 2), nullable=False),
        sa.Column("working_days", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        _now("updated_at"),
        sa.CheckConstraint(
            "weekly_hours >= 0 AND weekly_hours <= 168",
            name=op.f("ck_user_schedules_hours_range"),
        ),
        sa.CheckConstraint(
            "cardinality(working_days) >= 1", name=op.f("ck_user_schedules_has_days")
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name=op.f("fk_user_schedules_updated_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_schedules_user_id_users")
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_schedules")),
    )
    op.create_table(
        "reservations",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("hours_per_week", sa.Numeric(5, 2), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        _now("created_at"),
        _now("updated_at"),
        sa.CheckConstraint("end_date >= start_date", name=op.f("ck_reservations_dates_in_order")),
        sa.CheckConstraint(
            "hours_per_week > 0 AND hours_per_week <= 168",
            name=op.f("ck_reservations_hours_range"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_reservations_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_reservations_project_id_projects")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_reservations_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reservations")),
    )
    op.create_index(
        "ix_reservations_user_id_dates", "reservations", ["user_id", "start_date", "end_date"]
    )
    op.create_index("ix_reservations_project_id", "reservations", ["project_id"])
    op.create_table(
        "milestone_late_alerts",
        sa.Column("milestone_id", sa.Uuid(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        _now("sent_at"),
        sa.ForeignKeyConstraint(
            ["milestone_id"],
            ["milestones.id"],
            name=op.f("fk_milestone_late_alerts_milestone_id_milestones"),
        ),
        sa.PrimaryKeyConstraint("milestone_id", name=op.f("pk_milestone_late_alerts")),
    )


def downgrade() -> None:
    op.drop_table("milestone_late_alerts")
    op.drop_index("ix_reservations_project_id", table_name="reservations")
    op.drop_index("ix_reservations_user_id_dates", table_name="reservations")
    op.drop_table("reservations")
    op.drop_table("user_schedules")
    op.drop_table("workspace_schedule")
