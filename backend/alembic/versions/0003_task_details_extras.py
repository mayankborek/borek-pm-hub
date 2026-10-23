"""task comments, attachments (files and links), activity history

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-21
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.Column[Any]:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _stamp(name: str) -> sa.Column[Any]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "task_comments",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        _id(),
        _stamp("created_at"),
        _stamp("updated_at"),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name=op.f("fk_task_comments_task_id_tasks")
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_task_comments_author_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_comments")),
    )
    op.create_index(
        "ix_task_comments_task_id_created_at", "task_comments", ["task_id", "created_at"]
    )

    op.create_table(
        "task_attachments",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=2000), nullable=True),
        sa.Column("storage_key", sa.String(length=100), nullable=True),
        sa.Column("content_type", sa.String(length=150), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        _id(),
        _stamp("created_at"),
        _stamp("updated_at"),
        sa.CheckConstraint("kind IN ('file', 'link')", name=op.f("ck_task_attachments_kind")),
        sa.CheckConstraint(
            "(kind = 'link' AND url IS NOT NULL) OR (kind = 'file' AND storage_key IS NOT NULL)",
            name=op.f("ck_task_attachments_kind_matches_fields"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name=op.f("fk_task_attachments_task_id_tasks")
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"], ["users.id"], name=op.f("fk_task_attachments_uploaded_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_attachments")),
    )
    op.create_index(
        "ix_task_attachments_task_id_created_at", "task_attachments", ["task_id", "created_at"]
    )

    op.create_table(
        "task_activity",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column(
            "changes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        _id(),
        _stamp("created_at"),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name=op.f("fk_task_activity_task_id_tasks")
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_task_activity_actor_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_activity")),
    )
    op.create_index(
        "ix_task_activity_task_id_created_at", "task_activity", ["task_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("task_activity")
    op.drop_table("task_attachments")
    op.drop_table("task_comments")
