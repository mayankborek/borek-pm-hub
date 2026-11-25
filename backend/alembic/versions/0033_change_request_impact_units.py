"""change request impact as amount + unit (PM design spec 19.11.2026)

Replaces impact_schedule_days / impact_effort_hours with value + unit pairs. Existing
figures are kept: days -> (value, 'days'), hours -> (value, 'hours').

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UNITS = "('hours', 'days', 'weeks')"


def upgrade() -> None:
    for column in ("impact_schedule_value", "impact_effort_value"):
        op.add_column("change_requests", sa.Column(column, sa.Integer(), nullable=True))
    for column in ("impact_schedule_unit", "impact_effort_unit"):
        op.add_column("change_requests", sa.Column(column, sa.String(10), nullable=True))
    op.execute(
        "UPDATE change_requests SET impact_schedule_value = impact_schedule_days, "
        "impact_schedule_unit = 'days' WHERE impact_schedule_days IS NOT NULL"
    )
    op.execute(
        "UPDATE change_requests SET impact_effort_value = impact_effort_hours, "
        "impact_effort_unit = 'hours' WHERE impact_effort_hours IS NOT NULL"
    )
    op.drop_constraint(
        op.f("ck_change_requests_effort_not_negative"), "change_requests", type_="check"
    )
    op.drop_column("change_requests", "impact_schedule_days")
    op.drop_column("change_requests", "impact_effort_hours")
    op.create_check_constraint(
        op.f("ck_change_requests_impact_schedule_unit"),
        "change_requests",
        f"impact_schedule_unit IN {UNITS}",
    )
    op.create_check_constraint(
        op.f("ck_change_requests_impact_effort_unit"),
        "change_requests",
        f"impact_effort_unit IN {UNITS}",
    )
    op.create_check_constraint(
        op.f("ck_change_requests_impact_schedule_pair"),
        "change_requests",
        "(impact_schedule_value IS NULL) = (impact_schedule_unit IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_change_requests_impact_effort_pair"),
        "change_requests",
        "(impact_effort_value IS NULL) = (impact_effort_unit IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_change_requests_effort_not_negative"),
        "change_requests",
        "impact_effort_value IS NULL OR impact_effort_value >= 0",
    )


def downgrade() -> None:
    """Back to days / hours. Figures in another unit are converted (1 week = 7 days for the
    schedule; 1 day = 8 hours and 1 week = 40 hours for effort); hours of schedule round up
    to whole days."""
    for name in (
        "effort_not_negative",
        "impact_effort_pair",
        "impact_schedule_pair",
        "impact_effort_unit",
        "impact_schedule_unit",
    ):
        op.drop_constraint(op.f(f"ck_change_requests_{name}"), "change_requests", type_="check")
    op.add_column("change_requests", sa.Column("impact_schedule_days", sa.Integer()))
    op.add_column("change_requests", sa.Column("impact_effort_hours", sa.Integer()))
    op.execute(
        "UPDATE change_requests SET impact_schedule_days = CASE impact_schedule_unit "
        "WHEN 'weeks' THEN impact_schedule_value * 7 "
        "WHEN 'hours' THEN CEIL(impact_schedule_value / 24.0)::int "
        "ELSE impact_schedule_value END"
    )
    op.execute(
        "UPDATE change_requests SET impact_effort_hours = CASE impact_effort_unit "
        "WHEN 'weeks' THEN impact_effort_value * 40 "
        "WHEN 'days' THEN impact_effort_value * 8 "
        "ELSE impact_effort_value END"
    )
    for column in (
        "impact_schedule_value",
        "impact_schedule_unit",
        "impact_effort_value",
        "impact_effort_unit",
    ):
        op.drop_column("change_requests", column)
    op.create_check_constraint(
        op.f("ck_change_requests_effort_not_negative"),
        "change_requests",
        "impact_effort_hours IS NULL OR impact_effort_hours >= 0",
    )
