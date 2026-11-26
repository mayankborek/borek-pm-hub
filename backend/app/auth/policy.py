"""Configurable access (Administrator handoff 24.11.2026, screens 10 + 11, appendices A + B).

Pure data and small helpers, no database: `can()` uses them with facts the caller loaded.

Precedence (decided by Mayank 26.11.2026):
1. Fixed rules always win: inactive accounts, administrators, clients, admin-only actions and
   oversight (money, portfolio, access overview) are never changed by a switch.
2. A person's switch in a project (screen 10) wins over the role default.
3. The role default (screen 11) applies otherwise; it can only switch a right off, never give a
   role more than the built-in rules allow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from app.common.enums import GlobalRole

if TYPE_CHECKING:
    from app.auth.permissions import Action
    from app.users.models import User

# --- screen 11: role permissions -----------------------------------------------------------------

Cell = Literal["always", "on", "off", "none"]  # none = "--": this matrix does not configure it

CONFIGURABLE_ROLES = (
    GlobalRole.MANAGER,
    GlobalRole.PM,
    GlobalRole.ACCOUNT_MANAGER,
    GlobalRole.DEVELOPER,
)
MATRIX_ROLES = (*CONFIGURABLE_ROLES, GlobalRole.ADMIN, GlobalRole.CLIENT)


@dataclass(frozen=True)
class RolePermission:
    key: str
    label: str
    section: str
    # Action names this switch controls (empty: a navigation flag the frontend reads).
    actions: tuple[str, ...]
    defaults: dict[GlobalRole, Cell]


_M, _PM, _AM, _DEV, _ADM, _CL = (
    GlobalRole.MANAGER,
    GlobalRole.PM,
    GlobalRole.ACCOUNT_MANAGER,
    GlobalRole.DEVELOPER,
    GlobalRole.ADMIN,
    GlobalRole.CLIENT,
)


def _cells(m: Cell, pm: Cell, am: Cell, dev: Cell, adm: Cell, cl: Cell) -> dict[GlobalRole, Cell]:
    return {_M: m, _PM: pm, _AM: am, _DEV: dev, _ADM: adm, _CL: cl}


# Appendix A, in the order of the design.
ROLE_PERMISSIONS: tuple[RolePermission, ...] = (
    RolePermission(
        "dashboard",
        "Dashboard",
        "Workspace",
        (),
        _cells("always", "always", "always", "always", "none", "always"),
    ),
    RolePermission(
        "their_projects",
        "Their projects",
        "Workspace",
        (),
        _cells("always", "always", "always", "always", "none", "always"),
    ),
    RolePermission(
        "my_tasks",
        "My tasks",
        "Workspace",
        ("task:my_tasks",),
        _cells("off", "on", "on", "on", "none", "none"),
    ),
    RolePermission(
        "projects_menu",
        "Projects menu",
        "Workspace",
        (),
        _cells("on", "on", "on", "off", "none", "none"),
    ),
    RolePermission(
        "team_capacity",
        "Team capacity",
        "Team",
        ("team:view",),
        _cells("on", "none", "none", "none", "none", "none"),
    ),
    RolePermission(
        "team_workload",
        "Team workload",
        "Team",
        ("team:workload",),
        _cells("on", "none", "none", "none", "none", "none"),
    ),
    RolePermission(
        "create_projects",
        "Create projects",
        "Projects",
        ("project:create",),
        _cells("on", "on", "none", "none", "none", "none"),
    ),
    RolePermission(
        "manage_project_members",
        "Manage project members",
        "Projects",
        ("member:manage",),
        _cells("on", "on", "none", "none", "none", "none"),
    ),
    RolePermission(
        "set_project_status",
        "Set project status",
        "Projects",
        ("project:status",),
        _cells("on", "on", "none", "none", "none", "none"),
    ),
)
ROLE_PERMISSION_KEYS = {p.key: p for p in ROLE_PERMISSIONS}

# Set on the signed-in user for the request: {permission key: enabled} saved by an admin.
_POLICY_ATTR = "_role_policy_overrides"


def attach_role_policy(user: User, overrides: dict[str, bool]) -> None:
    setattr(user, _POLICY_ATTR, overrides)


def role_value(role: GlobalRole, key: str, overrides: dict[str, bool]) -> Cell:
    """The cell shown in the matrix: saved value for a configurable cell, else the default."""
    default = ROLE_PERMISSION_KEYS[key].defaults[role]
    if default in ("on", "off") and key in overrides:
        return "on" if overrides[key] else "off"
    return default


def role_policy_allows(user: User, action: Action) -> bool:
    """False when the user's role has a matrix switch for this action that is off."""
    try:
        role = GlobalRole(user.global_role)
    except ValueError:
        return True
    if role not in CONFIGURABLE_ROLES:
        return True
    overrides: dict[str, bool] = getattr(user, _POLICY_ATTR, None) or {}
    for permission in ROLE_PERMISSIONS:
        if action.value in permission.actions:
            if role_value(role, permission.key, overrides) == "off":
                return False
    return True


def navigation_flags(user: User) -> dict[str, bool]:
    """Every matrix row for the user's role as on/off, for the frontend (menus, pages)."""
    try:
        role = GlobalRole(user.global_role)
    except ValueError:
        return {}
    overrides: dict[str, bool] = getattr(user, _POLICY_ATTR, None) or {}
    return {p.key: role_value(role, p.key, overrides) in ("always", "on") for p in ROLE_PERMISSIONS}


# --- screen 10: a person's switches in one project -----------------------------------------------


@dataclass(frozen=True)
class ProjectControl:
    key: str
    label: str
    section: str
    action: str | None  # the action it switches; None = not configurable here (yet)


@dataclass(frozen=True)
class ControlSection:
    key: str
    label: str


PROJECT_SECTIONS: tuple[ControlSection, ...] = (
    ControlSection("project_overview", "Project overview"),
    ControlSection("tasks_and_board", "Tasks and board"),
    ControlSection("sprints_and_milestones", "Sprints and milestones"),
    ControlSection("change_requests", "Change requests"),
    ControlSection("people_and_access", "People and access"),
    ControlSection("reports_and_status", "Reports and project status"),
)


def _c(section: str, key: str, label: str, action: str | None) -> ProjectControl:
    return ProjectControl(key=key, label=label, section=section, action=action)


# Appendix B: 41 controls. Several controls switch the same server action (the API is not split
# that finely): turning one of them off blocks the action, turning one on allows it.
PROJECT_CONTROLS: tuple[ProjectControl, ...] = (
    _c("project_overview", "view_project", "View project page", "project:view"),
    _c("project_overview", "edit_project_details", "Edit project details", "project:update"),
    _c("project_overview", "change_project_status", "Change project status", "project:status"),
    _c("project_overview", "manage_project_phases", "Manage project phases", "milestone:manage"),
    _c("project_overview", "close_reopen_project", "Close or reopen project", "project:archive"),
    _c("tasks_and_board", "view_backlog_board", "View backlog and board", "task:view"),
    _c("tasks_and_board", "create_tasks", "Create tasks", "task:create"),
    _c(
        "tasks_and_board",
        "edit_task_title_description",
        "Edit task title and description",
        "task:edit_details",
    ),
    _c("tasks_and_board", "delete_tasks", "Delete tasks", "task:archive"),
    _c("tasks_and_board", "change_task_status", "Change task status", "task:change_status"),
    _c("tasks_and_board", "change_task_priority", "Change task priority", "task:edit_priority"),
    _c(
        "tasks_and_board",
        "change_task_type_labels",
        "Change task type and labels",
        "task:edit_details",
    ),
    _c(
        "tasks_and_board", "change_assignee_reporter", "Change assignee and reporter", "task:assign"
    ),
    _c("tasks_and_board", "change_estimate", "Change estimate", "task:edit_details"),
    _c("tasks_and_board", "change_task_dates", "Change task dates", "task:edit_schedule"),
    _c("tasks_and_board", "link_related_tasks", "Link related tasks", "task:link"),
    _c("tasks_and_board", "comment_on_tasks", "Comment on tasks", "task:comment"),
    _c("tasks_and_board", "request_changes_on_tasks", "Request changes on tasks", None),
    _c(
        "sprints_and_milestones",
        "view_sprints_milestones",
        "View sprints and milestones",
        None,  # follows "View backlog and board" / "View project page"
    ),
    _c("sprints_and_milestones", "create_edit_sprints", "Create and edit sprints", "sprint:manage"),
    _c(
        "sprints_and_milestones",
        "assign_tasks_to_sprint",
        "Assign tasks to a sprint",
        "sprint:manage",
    ),
    _c(
        "sprints_and_milestones",
        "start_complete_sprints",
        "Start and complete sprints",
        "sprint:manage",
    ),
    _c(
        "sprints_and_milestones",
        "create_edit_milestones",
        "Create and edit milestones",
        "milestone:manage",
    ),
    _c(
        "sprints_and_milestones",
        "assign_tasks_to_milestones",
        "Assign tasks to milestones",
        "milestone:manage",
    ),
    _c(
        "sprints_and_milestones",
        "mark_milestones_complete",
        "Mark milestones complete",
        "milestone:manage",
    ),
    _c("change_requests", "view_change_requests", "View change requests", "change_request:view"),
    _c(
        "change_requests",
        "submit_change_requests",
        "Submit change requests",
        "change_request:submit",
    ),
    _c(
        "change_requests",
        "discuss_change_requests",
        "Discuss change requests",
        "change_request:submit",
    ),
    _c(
        "change_requests",
        "review_change_requests",
        "Review change requests",
        "change_request:decide",
    ),
    _c(
        "change_requests",
        "edit_schedule_impact",
        "Add or edit schedule impact",
        "change_request:decide",
    ),
    _c(
        "change_requests",
        "approve_decline_change_requests",
        "Approve or decline change requests",
        "change_request:decide",
    ),
    _c(
        "change_requests",
        "apply_schedule_changes",
        "Apply approved schedule changes",
        "change_request:decide",
    ),
    _c("people_and_access", "view_project_members", "View project members", "people:view"),
    _c(
        "people_and_access",
        "add_remove_members",
        "Add or remove project members",
        "member:manage",
    ),
    _c(
        "people_and_access",
        "manage_member_access",
        "Manage project member access",
        "member:manage",
    ),
    _c(
        "people_and_access",
        "add_remove_client_contacts",
        "Add or remove client contacts",
        "member:manage",
    ),
    _c("people_and_access", "manage_stakeholders", "Manage stakeholders", "stakeholder:manage"),
    _c("reports_and_status", "view_status_reports", "View status reports", None),
    _c(
        "reports_and_status",
        "generate_edit_status_reports",
        "Generate and edit status reports",
        "status_report:manage",
    ),
    _c("reports_and_status", "download_reports", "Download reports", None),
    _c("reports_and_status", "share_reports", "Share reports", "status_report:manage"),
)
PROJECT_CONTROL_KEYS = {c.key: c for c in PROJECT_CONTROLS}
SECTION_KEYS = {s.key: s for s in PROJECT_SECTIONS}


def action_overrides(saved: dict[str, bool]) -> tuple[tuple[str, bool], ...]:
    """Saved control switches -> one answer per action. Off wins over on when two switches of
    the same action disagree."""
    result: dict[str, bool] = {}
    for key, enabled in saved.items():
        control = PROJECT_CONTROL_KEYS.get(key)
        if control is None or control.action is None:
            continue
        result[control.action] = result.get(control.action, True) and enabled
    return tuple(sorted(result.items()))
