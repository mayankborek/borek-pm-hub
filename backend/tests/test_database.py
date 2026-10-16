"""Database rules: constraints, indexes and optimistic locking (against real Postgres)."""

from datetime import date
from typing import Any

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.common.enums import GlobalRole, TaskStatus
from app.projects.models import Project, ProjectMember
from app.tasks.models import Task
from app.users.models import User
from tests.conftest import make_project, make_user


async def _task(session: AsyncSession, **overrides: Any) -> Task:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id)
    values: dict[str, Any] = {
        "project_id": project.id,
        "key": "TSK-001",
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
    assert task.status == "open"
    assert task.priority == "medium"
    assert task.progress == 0
    assert task.version == 1
    assert task.assignee_id is None  # unassigned tasks are allowed
    assert task.archived_at is None
    assert task.created_at.tzinfo is not None  # timestamptz


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "done"},
        {"priority": "urgent"},
        {"progress": 101},
        {"progress": -1},
        {"start_date": date(2026, 5, 10), "due_date": date(2026, 5, 1)},
        {"status": TaskStatus.BLOCKED.value},
        {"status": TaskStatus.BLOCKED.value, "blocked_reason": "   "},
    ],
)
async def test_invalid_task_is_rejected_by_the_database(
    session: AsyncSession, overrides: dict[str, Any]
) -> None:
    with pytest.raises(IntegrityError):
        await _task(session, **overrides)


async def test_blocked_task_with_reason_is_accepted(session: AsyncSession) -> None:
    task = await _task(session, status="blocked", blocked_reason="Waiting for credentials")
    assert task.id is not None


async def test_task_key_is_unique_per_project_only(session: AsyncSession) -> None:
    first = await _task(session)
    other_project = await make_project(session, first.created_by, code="OTHER")
    # Same key in another project is fine ...
    session.add(
        Task(project_id=other_project.id, key="TSK-001", title="x", created_by=first.created_by)
    )
    await session.flush()
    # ... but not twice in the same project.
    session.add(
        Task(project_id=first.project_id, key="TSK-001", title="y", created_by=first.created_by)
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
        "ix_tasks_project_id_status",
        "ix_tasks_assignee_id_status",
        "ix_tasks_project_id_due_date",
        "ix_tasks_project_id_updated_at",
    } <= found["tasks"]
    assert "ix_project_members_user_id" in found["project_members"]
