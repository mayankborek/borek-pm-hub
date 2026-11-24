"""risks / issues / decisions registers, RACI + communication role on stakeholders, picklists

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUS_FITS_KIND = (
    "(kind = 'risk' AND status IN ('open', 'mitigating', 'closed')) OR "
    "(kind = 'issue' AND status IN ('open', 'in_progress', 'resolved', 'closed')) OR "
    "(kind = 'decision' AND status IN ('proposed', 'decided', 'superseded'))"
)


def _stamps() -> list[sa.Column[object]]:
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
        "register_items",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("probability", sa.String(length=10), nullable=True),
        sa.Column("impact", sa.String(length=10), nullable=True),
        sa.Column("mitigation", sa.Text(), nullable=True),
        sa.Column("priority", sa.String(length=20), nullable=True),
        sa.Column("decided_on", sa.Date(), nullable=True),
        sa.Column("decided_by", sa.String(length=200), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        *_stamps(),
        sa.CheckConstraint(
            "kind IN ('risk', 'issue', 'decision')", name=op.f("ck_register_items_kind_valid")
        ),
        sa.CheckConstraint(STATUS_FITS_KIND, name=op.f("ck_register_items_status_fits_kind")),
        sa.CheckConstraint(
            "kind = 'risk' OR (probability IS NULL AND impact IS NULL AND mitigation IS NULL)",
            name=op.f("ck_register_items_risk_fields"),
        ),
        sa.CheckConstraint(
            "kind = 'issue' OR priority IS NULL", name=op.f("ck_register_items_issue_fields")
        ),
        sa.CheckConstraint(
            "kind = 'decision' OR (decided_on IS NULL AND decided_by IS NULL "
            "AND rationale IS NULL)",
            name=op.f("ck_register_items_decision_fields"),
        ),
        sa.CheckConstraint(
            "probability IS NULL OR probability IN ('low', 'medium', 'high')",
            name=op.f("ck_register_items_probability_valid"),
        ),
        sa.CheckConstraint(
            "impact IS NULL OR impact IN ('low', 'medium', 'high')",
            name=op.f("ck_register_items_impact_valid"),
        ),
        sa.CheckConstraint(
            "priority IS NULL OR priority IN ('highest', 'high', 'medium', 'low', 'lowest')",
            name=op.f("ck_register_items_priority_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_register_items_project_id_projects")
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_register_items_owner_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_register_items_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_register_items")),
        sa.UniqueConstraint("project_id", "code", name=op.f("uq_register_items_project_id_code")),
    )
    op.create_index("ix_register_items_project_id_kind", "register_items", ["project_id", "kind"])

    op.add_column("stakeholders", sa.Column("raci", sa.String(length=12), nullable=True))
    op.add_column(
        "stakeholders", sa.Column("communication_role", sa.String(length=200), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_stakeholders_raci"),
        "stakeholders",
        "raci IS NULL OR raci IN ('responsible', 'accountable', 'consulted', 'informed')",
    )

    op.create_table(
        "picklist_values",
        sa.Column("list_key", sa.String(length=50), nullable=False),
        sa.Column("value", sa.String(length=100), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        *_stamps(),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_picklist_values_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_picklist_values")),
    )
    op.create_index(
        "uq_picklist_values_list_key_value",
        "picklist_values",
        ["list_key", sa.text("lower(value)")],
        unique=True,
    )
    op.create_index(
        "ix_picklist_values_list_key_position", "picklist_values", ["list_key", "position"]
    )


def downgrade() -> None:
    op.drop_index("ix_picklist_values_list_key_position", table_name="picklist_values")
    op.drop_index("uq_picklist_values_list_key_value", table_name="picklist_values")
    op.drop_table("picklist_values")
    op.drop_constraint(op.f("ck_stakeholders_raci"), "stakeholders", type_="check")
    op.drop_column("stakeholders", "communication_role")
    op.drop_column("stakeholders", "raci")
    op.drop_index("ix_register_items_project_id_kind", table_name="register_items")
    op.drop_table("register_items")
