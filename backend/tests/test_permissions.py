"""The permission matrix (architecture section 8): role x action x member/not member/assignee."""

import re
import uuid
from pathlib import Path

import pytest

from app.auth.permissions import (
    Action,
    Resource,
    can,
    has_lead_rights,
    require,
    sees_all_projects,
)
from app.common.enums import GlobalRole
from app.core.errors import AppError
from app.users.models import User

PROJECT_ID = uuid.uuid4()
MEMBER = Resource(project_id=PROJECT_ID, is_member=True)
OUTSIDER = Resource(project_id=PROJECT_ID, is_member=False)


def make(role: GlobalRole, *, active: bool = True) -> User:
    return User(id=uuid.uuid4(), name="x", email="x@x", global_role=role.value, is_active=active)


@pytest.mark.parametrize("action", [a for a in Action if a is not Action.ADMIN_USERS])
def test_pm_can_do_everything_except_administration(action: Action) -> None:
    assert can(make(GlobalRole.PM), action, OUTSIDER)


@pytest.mark.parametrize("role", [GlobalRole.PM, GlobalRole.DEVELOPER])
def test_only_the_administrator_may_administer_users(role: GlobalRole) -> None:
    assert not can(make(role), Action.ADMIN_USERS)
    assert can(make(GlobalRole.ADMIN), Action.ADMIN_USERS)
    assert not can(make(GlobalRole.ADMIN, active=False), Action.ADMIN_USERS)


@pytest.mark.parametrize("action", [a for a in Action if a is not Action.ADMIN_USERS])
def test_administrator_has_no_access_to_project_data(action: Action) -> None:
    admin = make(GlobalRole.ADMIN)
    assert not can(admin, action)
    assert not can(admin, action, MEMBER)
    assert not sees_all_projects(admin)
    assert not has_lead_rights(admin)


@pytest.mark.parametrize(
    "role", [GlobalRole.MANAGER, GlobalRole.ACCOUNT_MANAGER, GlobalRole.CLIENT]
)
def test_roles_without_views_yet_can_do_nothing(role: GlobalRole) -> None:
    for action in Action:
        assert not can(make(role), action, MEMBER), action


@pytest.mark.parametrize(
    "action",
    [
        Action.PROJECT_CREATE,
        Action.PROJECT_UPDATE,
        Action.PROJECT_ARCHIVE,
        Action.MEMBER_MANAGE,
        Action.TASK_EDIT_DETAILS,
        Action.TASK_ASSIGN,
        Action.TASK_ARCHIVE,
        Action.TASK_IMPORT,
        Action.DASHBOARD_VIEW,
    ],
)
def test_developer_cannot_use_pm_only_actions_even_as_member(action: Action) -> None:
    assert not can(make(GlobalRole.DEVELOPER), action, MEMBER)


@pytest.mark.parametrize("action", [Action.PROJECT_LIST, Action.MY_TASKS])
def test_developer_can_list_projects_and_see_my_tasks(action: Action) -> None:
    assert can(make(GlobalRole.DEVELOPER), action)


@pytest.mark.parametrize("action", [Action.PROJECT_VIEW, Action.TASK_VIEW, Action.TASK_CREATE])
def test_developer_needs_membership_to_view_or_create(action: Action) -> None:
    developer = make(GlobalRole.DEVELOPER)
    assert can(developer, action, MEMBER)
    assert not can(developer, action, OUTSIDER)
    assert not can(developer, action)


def test_developer_changes_status_only_on_own_task_in_a_member_project() -> None:
    developer = make(GlobalRole.DEVELOPER)
    own = Resource(project_id=PROJECT_ID, is_member=True, assignee_id=developer.id)
    someone_elses = Resource(project_id=PROJECT_ID, is_member=True, assignee_id=uuid.uuid4())
    unassigned = Resource(project_id=PROJECT_ID, is_member=True)
    no_longer_member = Resource(project_id=PROJECT_ID, is_member=False, assignee_id=developer.id)
    assert can(developer, Action.TASK_CHANGE_STATUS, own)
    assert not can(developer, Action.TASK_CHANGE_STATUS, someone_elses)
    assert not can(developer, Action.TASK_CHANGE_STATUS, unassigned)
    assert not can(developer, Action.TASK_CHANGE_STATUS, no_longer_member)


def test_only_pm_and_project_lead_manage_statuses() -> None:
    developer = make(GlobalRole.DEVELOPER)
    lead = Resource(project_id=PROJECT_ID, is_member=True, is_project_lead=True)
    assert can(developer, Action.STATUS_MANAGE, lead)
    assert not can(developer, Action.STATUS_MANAGE, MEMBER)  # plain member
    assert not can(developer, Action.STATUS_MANAGE, OUTSIDER)
    assert not can(developer, Action.STATUS_MANAGE)
    not_member_any_more = Resource(project_id=PROJECT_ID, is_member=False, is_project_lead=True)
    assert not can(developer, Action.STATUS_MANAGE, not_member_any_more)


@pytest.mark.parametrize("role", list(GlobalRole))
def test_inactive_user_can_do_nothing(role: GlobalRole) -> None:
    assert not can(make(role, active=False), Action.PROJECT_LIST)


def test_unknown_role_can_do_nothing() -> None:
    user = make(GlobalRole.PM)
    user.global_role = "ghost"
    assert not can(user, Action.PROJECT_LIST)
    assert not can(user, Action.ADMIN_USERS)


def test_require_returns_404_for_a_non_member_and_403_for_a_member() -> None:
    developer = make(GlobalRole.DEVELOPER)
    with pytest.raises(AppError) as hidden:
        require(developer, Action.PROJECT_VIEW, OUTSIDER)
    assert hidden.value.status_code == 404
    with pytest.raises(AppError) as forbidden:
        require(developer, Action.PROJECT_UPDATE, MEMBER)
    assert forbidden.value.status_code == 403
    assert forbidden.value.code == "FORBIDDEN"


def test_require_returns_403_when_there_is_no_project_in_play() -> None:
    with pytest.raises(AppError) as error:
        require(make(GlobalRole.DEVELOPER), Action.PROJECT_CREATE)
    assert error.value.status_code == 403


def test_require_passes_silently_when_allowed() -> None:
    require(make(GlobalRole.PM), Action.PROJECT_CREATE)


def test_developer_changes_priority_only_on_own_task() -> None:
    developer = make(GlobalRole.DEVELOPER)
    own = Resource(project_id=PROJECT_ID, is_member=True, assignee_id=developer.id)
    someone_elses = Resource(project_id=PROJECT_ID, is_member=True, assignee_id=uuid.uuid4())
    unassigned = Resource(project_id=PROJECT_ID, is_member=True)
    no_longer_member = Resource(project_id=PROJECT_ID, is_member=False, assignee_id=developer.id)
    assert can(developer, Action.TASK_EDIT_PRIORITY, own)
    assert not can(developer, Action.TASK_EDIT_PRIORITY, someone_elses)
    assert not can(developer, Action.TASK_EDIT_PRIORITY, unassigned)
    assert not can(developer, Action.TASK_EDIT_PRIORITY, no_longer_member)


# --- role helpers (S2-01): today they mean exactly "is a PM" -------------------------------------


@pytest.mark.parametrize(
    ("role", "expected"), [(GlobalRole.PM, True), (GlobalRole.DEVELOPER, False)]
)
def test_role_helpers_match_the_old_pm_check(role: GlobalRole, expected: bool) -> None:
    user = make(role)
    assert sees_all_projects(user) is expected
    assert has_lead_rights(user) is expected


_ROLE_CHECK = re.compile(r"GlobalRole\.[A-Z_]+|global_role\s*[!=]=\s*[\"']")


def test_no_role_comparison_outside_the_permission_module() -> None:
    """New roles must only change `permissions.py`: no other module checks a specific role,
    neither through the enum (`GlobalRole.PM`) nor as a string (`global_role == "pm"`)."""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    allowed = {app_dir / "auth" / "permissions.py", app_dir / "common" / "enums.py"}
    offenders = [
        f"{path.relative_to(app_dir)}:{number}"
        for path in app_dir.rglob("*.py")
        if path not in allowed
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _ROLE_CHECK.search(line)
    ]
    assert offenders == []
