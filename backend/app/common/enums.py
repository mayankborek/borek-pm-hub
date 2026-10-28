"""Shared enums. Stored as varchar + CHECK constraints (not native Postgres enums)."""

from enum import StrEnum


class GlobalRole(StrEnum):
    PM = "pm"
    DEVELOPER = "developer"


class ProjectStatus(StrEnum):
    # Values are proposed, to be confirmed by the PM (Blockers, point 5).
    PLANNED = "planned"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ProjectRole(StrEnum):
    PROJECT_LEAD = "project_lead"
    DEVELOPER = "developer"


class MembershipSource(StrEnum):
    INVITATION = "invitation"
    TASK_ASSIGNMENT = "task_assignment"


class StatusCategory(StrEnum):
    """Every project status belongs to one category; dashboards and "overdue" use the category."""

    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"


class AttachmentKind(StrEnum):
    FILE = "file"
    LINK = "link"


class TaskPriority(StrEnum):
    HIGHEST = "highest"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    LOWEST = "lowest"


class EstimateUnit(StrEnum):
    MINUTES = "minutes"
    HOURS = "hours"
    WEEKS = "weeks"


def sql_in(column: str, enum: type[StrEnum]) -> str:
    """Build the text of a CHECK constraint: column IN ('a', 'b', ...)."""
    values = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"
