"""sprints (Jira-like: planned -> active -> completed), the sprint history per task, and the
task -> sprint link (no sprint = backlog)

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sprints",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("state", sa.String(length=20), server_default="planned", nullable=False),
        sa.Column("committed_count", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_by", sa.Uuid(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by", sa.Uuid(), nullable=True),
        sa.Column("spilled_to_sprint_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint(
            "state IN ('planned', 'active', 'completed')", name=op.f("ck_sprints_state_valid")
        ),
        sa.CheckConstraint("end_date >= start_date", name=op.f("ck_sprints_dates_order")),
        sa.CheckConstraint(
            "state = 'planned' OR (start_date IS NOT NULL AND end_date IS NOT NULL)",
            name=op.f("ck_sprints_dates_when_started"),
        ),
        sa.CheckConstraint(
            "(started_at IS NULL) = (state = 'planned')", name=op.f("ck_sprints_started_pair")
        ),
        sa.CheckConstraint(
            "(completed_at IS NULL) = (state <> 'completed')",
            name=op.f("ck_sprints_completed_pair"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_sprints_project_id_projects")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_sprints_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["started_by"], ["users.id"], name=op.f("fk_sprints_started_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["completed_by"], ["users.id"], name=op.f("fk_sprints_completed_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["spilled_to_sprint_id"],
            ["sprints.id"],
            name=op.f("fk_sprints_spilled_to_sprint_id_sprints"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sprints")),
        sa.UniqueConstraint("project_id", "number", name=op.f("uq_sprints_project_id_number")),
        sa.UniqueConstraint("id", "project_id", name=op.f("uq_sprints_id_project_id")),
    )
    op.create_index("ix_sprints_project_id_state", "sprints", ["project_id", "state"])
    op.create_index(
        "uq_sprints_one_active_per_project",
        "sprints",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("state = 'active'"),
    )

    op.create_table(
        "sprint_task_outcomes",
        sa.Column("sprint_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("status_name", sa.String(length=50), nullable=False),
        sa.Column("moved_to_sprint_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "outcome IN ('done', 'spilled')", name=op.f("ck_sprint_task_outcomes_outcome_valid")
        ),
        sa.ForeignKeyConstraint(
            ["sprint_id"],
            ["sprints.id"],
            name=op.f("fk_sprint_task_outcomes_sprint_id_sprints"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_sprint_task_outcomes_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["moved_to_sprint_id"],
            ["sprints.id"],
            name=op.f("fk_sprint_task_outcomes_moved_to_sprint_id_sprints"),
        ),
        sa.PrimaryKeyConstraint("sprint_id", "task_id", name=op.f("pk_sprint_task_outcomes")),
    )
    op.create_index("ix_sprint_task_outcomes_task_id", "sprint_task_outcomes", ["task_id"])

    op.add_column("tasks", sa.Column("sprint_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_tasks_sprint_id_sprints",
        "tasks",
        "sprints",
        ["sprint_id", "project_id"],
        ["id", "project_id"],
    )
    op.create_index("ix_tasks_sprint_id", "tasks", ["sprint_id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_sprint_id", table_name="tasks")
    op.drop_constraint("fk_tasks_sprint_id_sprints", "tasks", type_="foreignkey")
    op.drop_column("tasks", "sprint_id")
    op.drop_index("ix_sprint_task_outcomes_task_id", table_name="sprint_task_outcomes")
    op.drop_table("sprint_task_outcomes")
    op.drop_index("uq_sprints_one_active_per_project", table_name="sprints")
    op.drop_index("ix_sprints_project_id_state", table_name="sprints")
    op.drop_table("sprints")
