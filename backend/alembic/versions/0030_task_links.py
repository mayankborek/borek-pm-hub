"""task links (blocks, relates to, duplicates, clones) inside one project

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_links",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_task_id", sa.Uuid(), nullable=False),
        sa.Column("target_task_id", sa.Uuid(), nullable=False),
        sa.Column("link_type", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("source_task_id <> target_task_id", name=op.f("ck_task_links_not_self")),
        sa.CheckConstraint(
            "link_type IN ('blocks', 'relates_to', 'duplicates', 'clones')",
            name=op.f("ck_task_links_type_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_task_links_project_id_projects")
        ),
        sa.ForeignKeyConstraint(
            ["source_task_id"],
            ["tasks.id"],
            name=op.f("fk_task_links_source_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_task_id"],
            ["tasks.id"],
            name=op.f("fk_task_links_target_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_task_links_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_links")),
        sa.UniqueConstraint(
            "source_task_id",
            "target_task_id",
            "link_type",
            name=op.f("uq_task_links_source_task_id_target_task_id_link_type"),
        ),
    )
    op.create_index("ix_task_links_target_task_id", "task_links", ["target_task_id"])


def downgrade() -> None:
    op.drop_index("ix_task_links_target_task_id", table_name="task_links")
    op.drop_table("task_links")
