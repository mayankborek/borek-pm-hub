from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.projects.models import Project
from app.tasks.models import Task, WorkflowStatus
from app.users.models import User
from scripts import seed as seed_module
from scripts.seed import seed


async def test_seed_covers_every_demo_case(session: AsyncSession) -> None:
    await seed(session)
    today = datetime.now(UTC).date()

    users = (await session.execute(select(User))).scalars().all()
    assert sum(u.global_role == "pm" for u in users) == 1
    assert sum(u.global_role == "developer" for u in users) >= 2

    rows = (await session.execute(select(Task, WorkflowStatus).join(WorkflowStatus))).all()
    tasks = [(task, status.category) for task, status in rows]
    assert any(t.assignee_id is None and cat == "todo" for t, cat in tasks)  # unassigned
    assert any(cat == "blocked" and t.blocked_reason and t.blocked_at for t, cat in tasks)
    assert any(cat == "done" and t.completed_at for t, cat in tasks)
    assert any(t.archived_at for t, _ in tasks)  # archived
    assert any(t.labels for t, _ in tasks)
    assert any(t.due_date and t.due_date < today and cat != "done" for t, cat in tasks)  # overdue

    # Task keys are <CODE>-1.. per project and match each project's counter.
    for project in (await session.execute(select(Project))).scalars():
        keys = (
            (await session.execute(select(Task.key).where(Task.project_id == project.id)))
            .scalars()
            .all()
        )
        assert sorted(keys) == sorted(
            f"{project.code}-{n}" for n in range(1, project.task_counter + 1)
        )
        defaults = await session.scalar(
            select(func.count(WorkflowStatus.id)).where(WorkflowStatus.project_id == project.id)
        )
        assert defaults == 7


async def test_seed_refuses_to_run_twice(session: AsyncSession) -> None:
    await seed(session)
    with pytest.raises(SystemExit):
        await seed(session)
    assert (await session.execute(select(func.count()).select_from(User))).scalar_one() == 4


def test_seed_refuses_production(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(_env_file=None, environment="production", auth_mode="entra")
    monkeypatch.setattr(seed_module, "get_settings", lambda: settings)
    with pytest.raises(SystemExit):
        seed_module.check_environment()
