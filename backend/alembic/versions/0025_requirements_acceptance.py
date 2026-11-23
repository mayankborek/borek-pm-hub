"""requirements with versions, and the client's acceptance answer per published version

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
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
    op.create_table(
        "requirements",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("milestone_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="draft", nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        *_base(),
        sa.CheckConstraint(
            "status IN ('draft', 'awaiting_acceptance', 'changes_requested', 'accepted', "
            "'rejected')",
            name=op.f("ck_requirements_status"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_requirements_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["milestone_id", "project_id"],
            ["milestones.id", "milestones.project_id"],
            name="fk_requirements_milestone_id_milestones",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_requirements_owner_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_requirements_project_id_projects")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requirements")),
        sa.UniqueConstraint("project_id", "code", name=op.f("uq_requirements_project_id_code")),
    )
    op.create_index("ix_requirements_project_id_status", "requirements", ["project_id", "status"])
    op.create_index("ix_requirements_milestone_id", "requirements", ["milestone_id"])

    op.create_table(
        "requirement_versions",
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "acceptance_criteria",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.Uuid(), nullable=True),
        sa.Column("response", sa.String(length=30), nullable=True),
        sa.Column("response_comment", sa.Text(), nullable=True),
        sa.Column("responded_by", sa.Uuid(), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        *_base(),
        sa.CheckConstraint("number >= 1", name=op.f("ck_requirement_versions_number_positive")),
        sa.CheckConstraint(
            "response IS NULL OR response IN ('accepted', 'changes_requested', 'rejected')",
            name=op.f("ck_requirement_versions_response"),
        ),
        sa.CheckConstraint(
            "(response IS NULL) = (responded_at IS NULL)",
            name=op.f("ck_requirement_versions_responded_when_set"),
        ),
        sa.CheckConstraint(
            "response IS NULL OR published_at IS NOT NULL",
            name=op.f("ck_requirement_versions_answer_published"),
        ),
        sa.CheckConstraint(
            "(published_at IS NULL) = (published_by IS NULL)",
            name=op.f("ck_requirement_versions_published_by_when_published"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_requirement_versions_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["published_by"], ["users.id"], name=op.f("fk_requirement_versions_published_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["requirements.id"],
            name=op.f("fk_requirement_versions_requirement_id_requirements"),
        ),
        sa.ForeignKeyConstraint(
            ["responded_by"], ["users.id"], name=op.f("fk_requirement_versions_responded_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requirement_versions")),
        sa.UniqueConstraint(
            "requirement_id", "number", name=op.f("uq_requirement_versions_requirement_id_number")
        ),
    )


def downgrade() -> None:
    op.drop_table("requirement_versions")
    op.drop_index("ix_requirements_milestone_id", table_name="requirements")
    op.drop_index("ix_requirements_project_id_status", table_name="requirements")
    op.drop_table("requirements")
