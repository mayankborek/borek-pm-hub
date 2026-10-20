"""per-project custom statuses, labels, blocked_at, <code>-<n> task keys

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (name, category, old task status it replaces)
DEFAULTS = [
    ("Backlog", "backlog"),
    ("To do", "todo"),
    ("In progress", "in_progress"),
    ("Code review", "in_progress"),
    ("Testing", "in_progress"),
    ("Blocked", "blocked"),
    ("Done", "done"),
]
OLD_TO_NEW = {
    "open": "To do",
    "in_progress": "In progress",
    "blocked": "Blocked",
    "in_review": "Code review",
    "completed": "Done",
    "cancelled": "Done",  # cancelled tasks are archived below
}
CATEGORY_TO_OLD = {
    "backlog": "open",
    "todo": "open",
    "in_progress": "in_progress",
    "blocked": "blocked",
    "done": "completed",
}


def upgrade() -> None:
    op.create_table(
        "project_statuses",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
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
            "category IN ('backlog', 'todo', 'in_progress', 'blocked', 'done')",
            name=op.f("ck_project_statuses_category"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_project_statuses_project_id_projects")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_statuses")),
        sa.UniqueConstraint("project_id", "name", name=op.f("uq_project_statuses_project_id_name")),
        sa.UniqueConstraint("id", "project_id", name=op.f("uq_project_statuses_id_project_id")),
    )
    op.create_index(
        "ix_project_statuses_project_id_position",
        "project_statuses",
        ["project_id", "position"],
        unique=False,
    )

    # Default statuses for every existing project.
    for position, (name, category) in enumerate(DEFAULTS):
        op.execute(
            sa.text(
                "INSERT INTO project_statuses (project_id, name, category, position) "
                "SELECT id, :name, :category, :position FROM projects"
            ).bindparams(name=name, category=category, position=position)
        )

    # tasks: new columns first, then move the data, then drop the old status.
    op.add_column("tasks", sa.Column("status_id", sa.Uuid(), nullable=True))
    op.add_column(
        "tasks",
        sa.Column(
            "labels",
            postgresql.ARRAY(sa.String(length=30)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    op.add_column("tasks", sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True))
    for old, new_name in OLD_TO_NEW.items():
        op.execute(
            sa.text(
                "UPDATE tasks t SET status_id = s.id FROM project_statuses s "
                "WHERE s.project_id = t.project_id AND s.name = :new AND t.status = :old"
            ).bindparams(new=new_name, old=old)
        )
    op.execute(
        "UPDATE tasks SET archived_at = now() WHERE status = 'cancelled' AND archived_at IS NULL"
    )
    op.execute("UPDATE tasks SET blocked_at = updated_at WHERE status = 'blocked'")
    op.alter_column("tasks", "status_id", nullable=False)

    # Task keys: TSK-007 -> <project code>-7.
    op.alter_column("tasks", "key", type_=sa.String(length=32), existing_nullable=False)
    op.execute(
        "UPDATE tasks t SET key = p.code || '-' || (substr(t.key, 5))::int "
        "FROM projects p WHERE p.id = t.project_id AND t.key LIKE 'TSK-%'"
    )

    op.drop_index("ix_tasks_project_id_status", table_name="tasks")
    op.drop_index("ix_tasks_assignee_id_status", table_name="tasks")
    op.drop_constraint(op.f("ck_tasks_status"), "tasks", type_="check")
    op.drop_constraint(op.f("ck_tasks_blocked_needs_reason"), "tasks", type_="check")
    op.drop_column("tasks", "status")
    op.create_foreign_key(
        op.f("fk_tasks_status_id_project_statuses"),
        "tasks",
        "project_statuses",
        ["status_id", "project_id"],
        ["id", "project_id"],
    )
    op.create_index("ix_tasks_project_id_status_id", "tasks", ["project_id", "status_id"])
    op.create_index("ix_tasks_assignee_id_status_id", "tasks", ["assignee_id", "status_id"])


def downgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("status", sa.String(length=20), server_default="open", nullable=False),
    )
    for category, old in CATEGORY_TO_OLD.items():
        op.execute(
            sa.text(
                "UPDATE tasks t SET status = :old FROM project_statuses s "
                "WHERE s.id = t.status_id AND s.category = :category"
            ).bindparams(old=old, category=category)
        )
    # A blocked task needs a reason in the old schema.
    op.execute(
        "UPDATE tasks SET blocked_reason = 'Blocked' "
        "WHERE status = 'blocked' AND (blocked_reason IS NULL OR btrim(blocked_reason) = '')"
    )
    op.drop_index("ix_tasks_assignee_id_status_id", table_name="tasks")
    op.drop_index("ix_tasks_project_id_status_id", table_name="tasks")
    op.drop_constraint(op.f("fk_tasks_status_id_project_statuses"), "tasks", type_="foreignkey")
    op.drop_column("tasks", "status_id")
    op.drop_column("tasks", "blocked_at")
    op.drop_column("tasks", "labels")
    op.create_check_constraint(
        op.f("ck_tasks_status"),
        "tasks",
        "status IN ('open', 'in_progress', 'blocked', 'in_review', 'completed', 'cancelled')",
    )
    op.create_check_constraint(
        op.f("ck_tasks_blocked_needs_reason"),
        "tasks",
        "status <> 'blocked' OR (blocked_reason IS NOT NULL AND btrim(blocked_reason) <> '')",
    )
    op.create_index("ix_tasks_project_id_status", "tasks", ["project_id", "status"])
    op.create_index("ix_tasks_assignee_id_status", "tasks", ["assignee_id", "status"])
    # Task keys keep the new <code>-<n> format; they are only labels.
    op.drop_index("ix_project_statuses_project_id_position", table_name="project_statuses")
    op.drop_table("project_statuses")
