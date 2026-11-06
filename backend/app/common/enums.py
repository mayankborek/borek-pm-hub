"""Shared enums. Stored as varchar + CHECK constraints (not native Postgres enums)."""

from enum import StrEnum


class GlobalRole(StrEnum):
    ADMIN = "admin"
    PM = "pm"
    DEVELOPER = "developer"
    MANAGER = "manager"
    ACCOUNT_MANAGER = "account_manager"
    # Client exists so the database accepts it, but it has no views or rights yet (`can()` denies
    # it everything), so the admin API does not offer it.
    CLIENT = "client"


# The roles an administrator may give today (Sprint 02-26 plan, Admin Accounts Plan).
ASSIGNABLE_GLOBAL_ROLES = (
    GlobalRole.ADMIN,
    GlobalRole.MANAGER,
    GlobalRole.ACCOUNT_MANAGER,
    GlobalRole.PM,
    GlobalRole.DEVELOPER,
)


# How the roles are called on screen (names from the design).
GLOBAL_ROLE_LABELS = {
    GlobalRole.ADMIN: "Administrator",
    GlobalRole.MANAGER: "Manager",
    GlobalRole.ACCOUNT_MANAGER: "Account Manager",
    GlobalRole.PM: "Project Manager",
    GlobalRole.DEVELOPER: "Developer",
    GlobalRole.CLIENT: "Client",
}


class OrganisationType(StrEnum):
    INTERNAL = "internal"
    CLIENT = "client"


class RagStatus(StrEnum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"


class ReportState(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class StakeholderInfluence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FinanceEntryKind(StrEnum):
    PAYMENT = "payment"  # money the client paid
    SPEND = "spend"  # money spent on the project


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
