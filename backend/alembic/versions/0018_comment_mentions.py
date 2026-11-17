"""comment mentions: who is @mentioned in a task comment, by id

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_comment_mentions",
        sa.Column("comment_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["comment_id"],
            ["task_comments.id"],
            name=op.f("fk_task_comment_mentions_comment_id_task_comments"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_task_comment_mentions_user_id_users")
        ),
        sa.PrimaryKeyConstraint("comment_id", "user_id", name=op.f("pk_task_comment_mentions")),
    )
    op.create_index(op.f("ix_task_comment_mentions_user_id"), "task_comment_mentions", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_task_comment_mentions_user_id"), table_name="task_comment_mentions")
    op.drop_table("task_comment_mentions")
