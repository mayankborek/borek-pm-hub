"""The permission matrix (architecture section 8): role x action x member/not member/assignee."""

import uuid

import pytest

from app.auth.permissions import Action, Resource, can, require
from app.common.enums import GlobalRole
from app.core.errors import AppError
from app.users.models import User

PROJECT_ID = uuid.uuid4()
MEMBER = Resource(project_id=PROJECT_ID, is_member=True)
OUTSIDER = Resource(project_id=PROJECT_ID, is_member=False)


def make(role: GlobalRole, *, active: bool = True) -> User:
    return User(id=uuid.uuid4(), name="x", email="x@x", global_role=role.value, is_active=active)


@pytest.mark.parametrize("action", list(Action))
def test_pm_can_do_everything(action: Action) -> None:
    assert can(make(GlobalRole.PM), action, OUTSIDER)


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
    user.global_role = "admin"
    assert not can(user, Action.PROJECT_LIST)


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
