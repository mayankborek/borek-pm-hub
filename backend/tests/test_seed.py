from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.projects.models import Project
from app.tasks.models import Task
from app.users.models import User
from scripts import seed as seed_module
from scripts.seed import seed


async def test_seed_covers_every_demo_case(session: AsyncSession) -> None:
    await seed(session)
    today = datetime.now(UTC).date()

    users = (await session.execute(select(User))).scalars().all()
    assert sum(u.global_role == "pm" for u in users) == 1
    assert sum(u.global_role == "developer" for u in users) >= 2

    tasks = (await session.execute(select(Task))).scalars().all()
    assert any(t.assignee_id is None and t.status == "open" for t in tasks)  # unassigned
    assert any(t.status == "blocked" and t.blocked_reason for t in tasks)  # blocked
    assert any(t.status == "completed" for t in tasks)
    assert any(t.status == "cancelled" for t in tasks)
    assert any(
        t.due_date and t.due_date < today and t.status not in ("completed", "cancelled")
        for t in tasks
    )  # overdue

    # Task keys are TSK-001.. per project and match each project's counter.
    for project in (await session.execute(select(Project))).scalars():
        keys = (
            (await session.execute(select(Task.key).where(Task.project_id == project.id)))
            .scalars()
            .all()
        )
        assert sorted(keys) == [f"TSK-{n:03d}" for n in range(1, project.task_counter + 1)]


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
