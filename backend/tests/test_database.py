"""Database rules: constraints, indexes and optimistic locking (against real Postgres)."""

from datetime import date
from typing import Any

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.common.enums import GlobalRole
from app.projects.models import Project, ProjectMember
from app.tasks.models import Task, WorkflowStatus
from app.users.models import User
from tests.conftest import make_project, make_user, status_by_name


async def _task(session: AsyncSession, **overrides: Any) -> Task:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id)
    todo = await status_by_name(session, project.id, "To do")
    values: dict[str, Any] = {
        "project_id": project.id,
        "status_id": todo.id,
        "key": "PRJ-1",
        "title": "A task",
        "created_by": pm.id,
    }
    values.update(overrides)
    task = Task(**values)
    session.add(task)
    await session.flush()
    return task


async def test_defaults_are_applied(session: AsyncSession) -> None:
    task = await _task(session)
    await session.refresh(task)
    assert (await session.get(WorkflowStatus, task.status_id)).name == "To do"  # type: ignore[union-attr]
    assert task.labels == []
    assert task.priority == "medium"
    assert task.estimate_value is None and task.estimate_unit is None
    assert task.version == 1
    assert task.assignee_id is None  # unassigned tasks are allowed
    assert task.archived_at is None
    assert task.created_at.tzinfo is not None  # timestamptz


@pytest.mark.parametrize(
    "overrides",
    [
        {"priority": "urgent"},
        {"estimate_value": 5},  # amount without a unit
        {"estimate_unit": "hours"},  # unit without an amount
        {"estimate_value": 0, "estimate_unit": "hours"},
        {"estimate_value": 3, "estimate_unit": "days"},
        {"start_date": date(2026, 5, 10), "due_date": date(2026, 5, 1)},
    ],
)
async def test_invalid_task_is_rejected_by_the_database(
    session: AsyncSession, overrides: dict[str, Any]
) -> None:
    with pytest.raises(IntegrityError):
        await _task(session, **overrides)


async def test_task_cannot_use_another_projects_status(session: AsyncSession) -> None:
    first = await _task(session)
    other = await make_project(session, first.created_by, code="OTHER")
    foreign = await status_by_name(session, other.id, "To do")
    first.status_id = foreign.id
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_status_names_are_unique_per_project(session: AsyncSession) -> None:
    task = await _task(session)
    session.add(
        WorkflowStatus(project_id=task.project_id, name="To do", category="todo", position=99)
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_status_category_is_checked(session: AsyncSession) -> None:
    task = await _task(session)
    session.add(
        WorkflowStatus(project_id=task.project_id, name="Odd", category="weird", position=99)
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_task_key_is_unique_per_project_only(session: AsyncSession) -> None:
    first = await _task(session)
    other_project = await make_project(session, first.created_by, code="OTHER")
    # Same key in another project is fine ...
    other_todo = await status_by_name(session, other_project.id, "To do")
    session.add(
        Task(
            project_id=other_project.id,
            status_id=other_todo.id,
            key="PRJ-1",
            title="x",
            created_by=first.created_by,
        )
    )
    await session.flush()
    # ... but not twice in the same project.
    session.add(
        Task(
            project_id=first.project_id,
            status_id=first.status_id,
            key="PRJ-1",
            title="y",
            created_by=first.created_by,
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_user_email_must_be_unique(session: AsyncSession) -> None:
    await make_user(session, email="same@test.example")
    with pytest.raises(IntegrityError):
        await make_user(session, email="same@test.example")


async def test_user_role_is_checked(session: AsyncSession) -> None:
    session.add(User(name="x", email="y@test.example", global_role="admin"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_project_code_must_be_unique(session: AsyncSession) -> None:
    pm = await make_user(session, GlobalRole.PM)
    await make_project(session, pm.id, code="DUP")
    with pytest.raises(IntegrityError):
        await make_project(session, pm.id, code="DUP")


async def test_project_end_date_cannot_precede_start_date(session: AsyncSession) -> None:
    pm = await make_user(session, GlobalRole.PM)
    session.add(
        Project(
            code="BAD",
            name="x",
            created_by=pm.id,
            start_date=date(2026, 6, 1),
            target_end_date=date(2026, 5, 1),
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_user_cannot_be_member_of_a_project_twice(session: AsyncSession) -> None:
    pm = await make_user(session, GlobalRole.PM)
    dev = await make_user(session)
    project = await make_project(session, pm.id)
    session.add(ProjectMember(project_id=project.id, user_id=dev.id))
    await session.flush()
    session.add(ProjectMember(project_id=project.id, user_id=dev.id))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_membership_role_is_checked(session: AsyncSession) -> None:
    pm = await make_user(session, GlobalRole.PM)
    dev = await make_user(session)
    project = await make_project(session, pm.id)
    session.add(ProjectMember(project_id=project.id, user_id=dev.id, project_role="boss"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_optimistic_locking_increments_version_and_detects_conflicts(
    session: AsyncSession,
) -> None:
    task = await _task(session)
    task.title = "Changed"
    await session.flush()
    await session.refresh(task)
    assert task.version == 2

    # Someone else updates the same row behind our back ...
    await session.execute(
        text("UPDATE tasks SET version = version + 1 WHERE id = :id"), {"id": task.id}
    )
    # ... so our next update (based on the old version) must fail instead of overwriting.
    task.title = "Changed again"
    with pytest.raises(StaleDataError):
        await session.flush()


async def test_required_indexes_exist(session: AsyncSession) -> None:
    def names(sync_session: Any) -> dict[str, set[str]]:
        inspector = inspect(sync_session.connection())
        return {
            table: {index["name"] for index in inspector.get_indexes(table)}
            for table in ("tasks", "project_members")
        }

    found = await session.run_sync(names)
    assert {
        "ix_tasks_project_id_status_id",
        "ix_tasks_assignee_id_status_id",
        "ix_tasks_project_id_due_date",
        "ix_tasks_project_id_updated_at",
    } <= found["tasks"]
    assert "ix_project_members_user_id" in found["project_members"]
