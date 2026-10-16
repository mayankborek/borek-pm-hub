"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-16 17:39:13.733228
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("global_role", sa.String(length=20), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.CheckConstraint("global_role IN ('pm', 'developer')", name=op.f("ck_users_global_role")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("external_id", name=op.f("uq_users_external_id")),
    )
    op.create_table(
        "projects",
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="planned", nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("target_end_date", sa.Date(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("task_counter", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('planned', 'active', 'on_hold', 'completed')",
            name=op.f("ck_projects_status"),
        ),
        sa.CheckConstraint(
            "target_end_date IS NULL OR start_date IS NULL OR target_end_date >= start_date",
            name=op.f("ck_projects_dates_order"),
        ),
        sa.CheckConstraint("task_counter >= 0", name=op.f("ck_projects_task_counter_non_negative")),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_projects_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
        sa.UniqueConstraint("code", name=op.f("uq_projects_code")),
    )
    op.create_table(
        "project_members",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_role", sa.String(length=20), server_default="developer", nullable=False),
        sa.Column("source", sa.String(length=20), server_default="invitation", nullable=False),
        sa.Column("granted_by", sa.Uuid(), nullable=True),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "project_role IN ('project_lead', 'developer')",
            name=op.f("ck_project_members_project_role"),
        ),
        sa.CheckConstraint(
            "source IN ('invitation', 'task_assignment')", name=op.f("ck_project_members_source")
        ),
        sa.ForeignKeyConstraint(
            ["granted_by"], ["users.id"], name=op.f("fk_project_members_granted_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_project_members_project_id_projects")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_project_members_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_members")),
        sa.UniqueConstraint(
            "project_id", "user_id", name=op.f("uq_project_members_project_id_user_id")
        ),
    )
    op.create_index("ix_project_members_user_id", "project_members", ["user_id"], unique=False)
    op.create_table(
        "tasks",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="open", nullable=False),
        sa.Column("priority", sa.String(length=20), server_default="medium", nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("progress", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("assignee_id", sa.Uuid(), nullable=True),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "priority IN ('critical', 'high', 'medium', 'low')", name=op.f("ck_tasks_priority")
        ),
        sa.CheckConstraint(
            "status <> 'blocked' OR (blocked_reason IS NOT NULL AND btrim(blocked_reason) <> '')",
            name=op.f("ck_tasks_blocked_needs_reason"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'blocked', 'in_review', 'completed', 'cancelled')",
            name=op.f("ck_tasks_status"),
        ),
        sa.CheckConstraint(
            "due_date IS NULL OR start_date IS NULL OR due_date >= start_date",
            name=op.f("ck_tasks_dates_order"),
        ),
        sa.CheckConstraint("progress BETWEEN 0 AND 100", name=op.f("ck_tasks_progress_range")),
        sa.ForeignKeyConstraint(
            ["assignee_id"], ["users.id"], name=op.f("fk_tasks_assignee_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_tasks_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_tasks_project_id_projects")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
        sa.UniqueConstraint("project_id", "key", name=op.f("uq_tasks_project_id_key")),
    )
    op.create_index("ix_tasks_assignee_id_status", "tasks", ["assignee_id", "status"], unique=False)
    op.create_index(
        "ix_tasks_project_id_due_date", "tasks", ["project_id", "due_date"], unique=False
    )
    op.create_index("ix_tasks_project_id_status", "tasks", ["project_id", "status"], unique=False)
    op.create_index(
        "ix_tasks_project_id_updated_at", "tasks", ["project_id", "updated_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_project_id_updated_at", table_name="tasks")
    op.drop_index("ix_tasks_project_id_status", table_name="tasks")
    op.drop_index("ix_tasks_project_id_due_date", table_name="tasks")
    op.drop_index("ix_tasks_assignee_id_status", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_project_members_user_id", table_name="project_members")
    op.drop_table("project_members")
    op.drop_table("projects")
    op.drop_table("users")
