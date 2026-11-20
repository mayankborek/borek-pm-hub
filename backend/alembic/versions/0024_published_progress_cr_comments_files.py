"""PM-published progress on status reports; change request comments and attachments

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base() -> list[sa.Column[object]]:
    return [
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.add_column("status_reports", sa.Column("progress_percent", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_status_reports_progress_range"),
        "status_reports",
        "progress_percent IS NULL OR progress_percent BETWEEN 0 AND 100",
    )

    op.create_table(
        "change_request_comments",
        sa.Column("change_request_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("internal", sa.Boolean(), server_default=sa.false(), nullable=False),
        *_base(),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_change_request_comments_author_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["change_request_id"],
            ["change_requests.id"],
            name=op.f("fk_change_request_comments_change_request_id_change_requests"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_request_comments")),
    )
    op.create_index(
        "ix_change_request_comments_request_id_created_at",
        "change_request_comments",
        ["change_request_id", "created_at"],
    )

    op.create_table(
        "change_request_attachments",
        sa.Column("change_request_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=100), nullable=False),
        sa.Column("content_type", sa.String(length=150), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        *_base(),
        sa.ForeignKeyConstraint(
            ["change_request_id"],
            ["change_requests.id"],
            name=op.f("fk_change_request_attachments_change_request_id_change_requests"),
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name=op.f("fk_change_request_attachments_uploaded_by_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_request_attachments")),
    )
    op.create_index(
        "ix_change_request_attachments_request_id_created_at",
        "change_request_attachments",
        ["change_request_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_change_request_attachments_request_id_created_at",
        table_name="change_request_attachments",
    )
    op.drop_table("change_request_attachments")
    op.drop_index(
        "ix_change_request_comments_request_id_created_at", table_name="change_request_comments"
    )
    op.drop_table("change_request_comments")
    op.drop_constraint(op.f("ck_status_reports_progress_range"), "status_reports", type_="check")
    op.drop_column("status_reports", "progress_percent")
