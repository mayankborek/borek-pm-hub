"""WHAT a user may do: the single `can()` function (architecture section 8).

Every endpoint calls `require()`; nothing else decides permissions. The caller loads the facts
about the resource (is the user a member, who is the assignee) and passes them in `Resource`,
so this module stays free of database access and is easy to test.
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import ColumnElement

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
    ADMIN_USERS = "admin:users"  # create, edit, deactivate users; invite links (admin only)
    AUDIT_VIEW = "audit:view"  # read the audit log (admin only)
    ORGANISATION_MANAGE = "organisation:manage"  # create, edit, archive; account managers
    ORGANISATION_VIEW = "organisation:view"  # read, for example to pick a project's client
    PORTFOLIO_VIEW = "portfolio:view"  # overview across projects (Manager, Account Manager)
    ACCESS_OVERVIEW = "access:overview"  # who is in which project (Manager)
    STATUS_REPORT_MANAGE = "status_report:manage"  # write and publish; see drafts
    STAKEHOLDER_MANAGE = "stakeholder:manage"  # read and change the register (contact details)
    FINANCE_MANAGE = "finance:manage"  # read and change budget and entries


@dataclass(frozen=True)
class Resource:
    """Facts about the thing being accessed. Leave empty for actions without a project."""

    project_id: uuid.UUID | None = None
    is_member: bool = False
    is_project_lead: bool = False
    is_account_manager: bool = False  # the project's client is assigned to this Account Manager
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
# A PM has these without being in any project; every other right depends on the project role.
_PM_WITHOUT_PROJECT = frozenset(
    {Action.PROJECT_CREATE, Action.DASHBOARD_VIEW, Action.USER_LIST, Action.ORGANISATION_VIEW}
)
# Oversight across projects and money: never part of a project lead's rights.
NOT_FOR_LEADS = frozenset({Action.PORTFOLIO_VIEW, Action.ACCESS_OVERVIEW, Action.FINANCE_MANAGE})
# Account Managers read, and handle reports, stakeholders and money; on a project only when its
# client is assigned to them.
_ACCOUNT_MANAGER_ANYWHERE = frozenset(
    {Action.PROJECT_LIST, Action.PORTFOLIO_VIEW, Action.ORGANISATION_VIEW}
)
_ACCOUNT_MANAGER_ON_PROJECT = frozenset(
    {
        Action.PROJECT_VIEW,
        Action.TASK_VIEW,
        Action.STATUS_REPORT_MANAGE,
        Action.STAKEHOLDER_MANAGE,
        Action.FINANCE_MANAGE,
    }
)
# Developers need project membership for these.
_MEMBER_ACTIONS = frozenset(
    {Action.PROJECT_VIEW, Action.TASK_VIEW, Action.TASK_CREATE, Action.TASK_COMMENT}
)
_ANY_USER = frozenset({Action.PROJECT_LIST, Action.MY_TASKS})
# The administrator can do these and nothing else; nobody else can do them (not even a PM).
ADMIN_ONLY = frozenset({Action.ADMIN_USERS, Action.AUDIT_VIEW, Action.ORGANISATION_MANAGE})


# --- role helpers -------------------------------------------------------------------------------
# The only place that maps global roles to "how much of the system" a user sees. Other modules
# call these instead of comparing `global_role`, so new roles change only this block.


def sees_all_projects(user: User) -> bool:
    """Sees every project, including archived ones, in lists, dashboards and project pages."""
    return user.global_role == GlobalRole.MANAGER


def may_lead_projects(user: User) -> bool:
    """A role that can run projects: a PM where they are project lead, a Manager everywhere."""
    return user.global_role in (GlobalRole.PM, GlobalRole.MANAGER)


def has_lead_rights(user: User, *, is_project_lead: bool = False) -> bool:
    """May do the lead's work in this project: edit and assign tasks, manage members, archive
    comments and attachments of others. A developer who is project lead only manages statuses."""
    return sees_all_projects(user) or (user.global_role == GlobalRole.PM and is_project_lead)


def is_admin(user: User) -> bool:
    return user.global_role == GlobalRole.ADMIN


def is_account_manager(user: User) -> bool:
    return user.global_role == GlobalRole.ACCOUNT_MANAGER


def account_manager_condition() -> ColumnElement[bool]:
    """SQL condition for "is an Account Manager" (only they can be assigned to a client)."""
    return User.global_role == GlobalRole.ACCOUNT_MANAGER.value


def admin_condition() -> ColumnElement[bool]:
    """SQL condition for "is an administrator" (the last-admin rule counts them)."""
    return User.global_role == GlobalRole.ADMIN.value


def works_on_tasks_condition() -> ColumnElement[bool]:
    """SQL condition for the roles that do project work, so the assignee picker lists only them."""
    return User.global_role.in_(
        [GlobalRole.PM.value, GlobalRole.DEVELOPER.value, GlobalRole.MANAGER.value]
    )


def can(user: User, action: Action, resource: Resource | None = None) -> bool:
    if not user.is_active:
        return False
    if is_admin(user):
        # No project data: denied by default.
        return action in ADMIN_ONLY or action is Action.ORGANISATION_VIEW
    if action in ADMIN_ONLY:
        return False
    if sees_all_projects(user):
        return True
    resource = resource or Resource()
    if is_account_manager(user):
        if action in _ACCOUNT_MANAGER_ON_PROJECT:
            return resource.is_account_manager
        return action in _ACCOUNT_MANAGER_ANYWHERE
    if action in NOT_FOR_LEADS:
        return False
    if user.global_role == GlobalRole.PM:
        if action in _PM_WITHOUT_PROJECT:
            return True
        if resource.is_member and has_lead_rights(user, is_project_lead=resource.is_project_lead):
            return True
        # Otherwise rights follow the project role: a plain member is treated like a developer.
    elif user.global_role != GlobalRole.DEVELOPER:
        return False
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
        and not resource.is_account_manager
    ):
        raise AppError(404, "NOT_FOUND", "Project not found.")
    raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
