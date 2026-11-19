"""project phases, milestones and the task -> milestone link (project roadmap)

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _common() -> list[sa.Column[object]]:
    return [
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "project_phases",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("client_visible", sa.Boolean(), server_default=sa.false(), nullable=False),
        *_common(),
        sa.CheckConstraint("end_date >= start_date", name=op.f("ck_project_phases_dates_order")),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_project_phases_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_project_phases_project_id_projects")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_phases")),
        sa.UniqueConstraint("id", "project_id", name=op.f("uq_project_phases_id_project_id")),
    )
    op.create_index(
        "ix_project_phases_project_id_position", "project_phases", ["project_id", "position"]
    )

    op.create_table(
        "milestones",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("phase_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("completion_criteria", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by", sa.Uuid(), nullable=True),
        sa.Column("at_risk", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("client_visible", sa.Boolean(), server_default=sa.false(), nullable=False),
        *_common(),
        sa.CheckConstraint(
            "(completed_at IS NULL) = (completed_by IS NULL)",
            name=op.f("ck_milestones_completed_pair"),
        ),
        sa.ForeignKeyConstraint(
            ["completed_by"], ["users.id"], name=op.f("fk_milestones_completed_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_milestones_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_milestones_owner_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["phase_id", "project_id"],
            ["project_phases.id", "project_phases.project_id"],
            name="fk_milestones_phase_id_project_phases",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_milestones_project_id_projects")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_milestones")),
        sa.UniqueConstraint("id", "project_id", name=op.f("uq_milestones_id_project_id")),
        sa.UniqueConstraint("project_id", "code", name=op.f("uq_milestones_project_id_code")),
    )
    op.create_index("ix_milestones_project_id_due_date", "milestones", ["project_id", "due_date"])

    op.add_column("tasks", sa.Column("milestone_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_tasks_milestone_id_milestones",
        "tasks",
        "milestones",
        ["milestone_id", "project_id"],
        ["id", "project_id"],
    )
    op.create_index("ix_tasks_milestone_id", "tasks", ["milestone_id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_milestone_id", table_name="tasks")
    op.drop_constraint("fk_tasks_milestone_id_milestones", "tasks", type_="foreignkey")
    op.drop_column("tasks", "milestone_id")
    op.drop_index("ix_milestones_project_id_due_date", table_name="milestones")
    op.drop_table("milestones")
    op.drop_index("ix_project_phases_project_id_position", table_name="project_phases")
    op.drop_table("project_phases")
