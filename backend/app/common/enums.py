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


class ProjectRole(StrEnum):
    PROJECT_LEAD = "project_lead"
    DEVELOPER = "developer"


class MembershipSource(StrEnum):
    INVITATION = "invitation"
    TASK_ASSIGNMENT = "task_assignment"


class TaskStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    IN_REVIEW = "in_review"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskPriority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def sql_in(column: str, enum: type[StrEnum]) -> str:
    """Build the text of a CHECK constraint: column IN ('a', 'b', ...)."""
    values = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"
