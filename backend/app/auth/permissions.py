"""WHAT a user may do: the single `can()` function (architecture section 8).

Every endpoint calls `require()`; nothing else decides permissions. The caller loads the facts
about the resource (is the user a member, who is the assignee) and passes them in `Resource`,
so this module stays free of database access and is easy to test.
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum

from app.common.enums import GlobalRole
from app.core.errors import AppError
from app.users.models import User


class Action(StrEnum):
    PROJECT_CREATE = "project:create"
    PROJECT_UPDATE = "project:update"
    PROJECT_ARCHIVE = "project:archive"
    PROJECT_LIST = "project:list"
    PROJECT_VIEW = "project:view"
    MEMBER_MANAGE = "member:manage"
    STATUS_MANAGE = "status:manage"  # add, rename, reorder, delete a project's statuses
    TASK_CREATE = "task:create"
    TASK_EDIT_DETAILS = "task:edit_details"  # title, description, labels, estimate
    TASK_EDIT_PRIORITY = "task:edit_priority"  # PM, or the developer the task is assigned to
    TASK_EDIT_SCHEDULE = "task:edit_schedule"  # start and due date
    TASK_ASSIGN = "task:assign"
    TASK_CHANGE_STATUS = "task:change_status"  # also covers blocked_reason
    TASK_VIEW = "task:view"
    TASK_COMMENT = "task:comment"  # comments and attachments
    TASK_ARCHIVE = "task:archive"
    TASK_IMPORT = "task:import"  # bring tasks in from a CSV file (Jira transfer)
    MY_TASKS = "task:my_tasks"
    DASHBOARD_VIEW = "dashboard:view"
    USER_LIST = "user:list"  # search users for the assignee picker


@dataclass(frozen=True)
class Resource:
    """Facts about the thing being accessed. Leave empty for actions without a project."""

    project_id: uuid.UUID | None = None
    is_member: bool = False
    is_project_lead: bool = False
    assignee_id: uuid.UUID | None = None
    creator_id: uuid.UUID | None = None


_PM_ONLY = frozenset(
    {
        Action.PROJECT_CREATE,
        Action.PROJECT_UPDATE,
        Action.PROJECT_ARCHIVE,
        Action.MEMBER_MANAGE,
        Action.TASK_EDIT_DETAILS,
        Action.TASK_ASSIGN,
        Action.TASK_ARCHIVE,
        Action.TASK_IMPORT,
        Action.DASHBOARD_VIEW,
        Action.USER_LIST,
    }
)
# Developers need project membership for these.
_MEMBER_ACTIONS = frozenset(
    {Action.PROJECT_VIEW, Action.TASK_VIEW, Action.TASK_CREATE, Action.TASK_COMMENT}
)
_ANY_USER = frozenset({Action.PROJECT_LIST, Action.MY_TASKS})


# --- role helpers -------------------------------------------------------------------------------
# The only place that maps global roles to "how much of the system" a user sees. Other modules
# call these instead of comparing `global_role`, so new roles change only this block.


def sees_all_projects(user: User) -> bool:
    """Sees every project, including archived ones, in lists, dashboards and project pages."""
    return user.global_role == GlobalRole.PM


def has_lead_rights(user: User) -> bool:
    """May do the lead's work on other people's items: assign tasks to anyone on creation,
    archive comments and attachments of others."""
    return user.global_role == GlobalRole.PM


def can(user: User, action: Action, resource: Resource | None = None) -> bool:
    if not user.is_active:
        return False
    if has_lead_rights(user):
        return True
    if user.global_role != GlobalRole.DEVELOPER:
        return False
    resource = resource or Resource()
    if action in _ANY_USER:
        return True
    if action in _MEMBER_ACTIONS:
        return resource.is_member
    if action is Action.STATUS_MANAGE:
        return resource.is_member and resource.is_project_lead
    if action is Action.TASK_EDIT_PRIORITY:
        # Never on tasks of other developers or on unassigned tasks.
        return resource.is_member and resource.assignee_id == user.id
    if action is Action.TASK_CHANGE_STATUS:
        # Only on tasks assigned to them (the allowed transitions are checked by the workflow).
        return resource.is_member and resource.assignee_id == user.id
    if action is Action.TASK_EDIT_SCHEDULE:
        # Dates of a task the developer created for themselves (they are creator and assignee).
        return (
            resource.is_member
            and resource.assignee_id == user.id
            and resource.creator_id == user.id
        )
    return False  # everything in _PM_ONLY and anything unknown


def require(user: User, action: Action, resource: Resource | None = None) -> None:
    """Raise 403, or 404 when a non-member should not even learn the project exists."""
    if can(user, action, resource):
        return
    if (
        resource is not None
        and resource.project_id is not None
        and not sees_all_projects(user)
        and not resource.is_member
    ):
        raise AppError(404, "NOT_FOUND", "Project not found.")
    raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
