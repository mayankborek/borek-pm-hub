from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password, verify_password
from app.common.enums import GlobalRole
from app.core.config import Settings
from app.projects.models import Project
from app.tasks.models import Task, WorkflowStatus
from app.users.models import User
from scripts import seed as seed_module
from scripts.seed import ensure_core_accounts, seed
from tests.conftest import make_project, make_user


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
    assert (await session.execute(select(func.count()).select_from(User))).scalar_one() == 7


def test_seed_refuses_production(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(_env_file=None, environment="production", auth_mode="entra")
    monkeypatch.setattr(seed_module, "get_settings", lambda: settings)
    with pytest.raises(SystemExit):
        seed_module.check_environment()


def test_seed_in_production_needs_the_flag_and_never_resets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(_env_file=None, environment="production", auth_mode="entra")
    monkeypatch.setattr(seed_module, "get_settings", lambda: settings)
    seed_module.check_environment(allow_production=True)  # allowed with the flag
    with pytest.raises(SystemExit):
        seed_module.check_environment(allow_production=True, do_reset=True)


def test_seed_password_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEED_USER_PASSWORD", raising=False)
    assert seed_module.read_seed_password() is None
    monkeypatch.setenv("SEED_USER_PASSWORD", "short")
    with pytest.raises(SystemExit):
        seed_module.read_seed_password()
    monkeypatch.setenv("SEED_USER_PASSWORD", "a-long-enough-password")
    assert seed_module.read_seed_password() == "a-long-enough-password"


async def test_seed_users_can_sign_in_when_a_password_is_given(session: AsyncSession) -> None:
    await seed(session, password="a-long-enough-password")
    users = (await session.execute(select(User))).scalars().all()
    assert len(users) == 7
    assert all(
        u.password_hash and verify_password("a-long-enough-password", u.password_hash)
        for u in users
    )


PASSWORD = "a-long-enough-password"


async def test_seed_has_an_administrator_and_a_manager(session: AsyncSession) -> None:
    await seed(session, password=PASSWORD)
    roles = {u.email: u.global_role for u in (await session.scalars(select(User))).all()}
    assert roles["admin@borek.test"] == "admin"
    assert roles["manager@borek.test"] == "manager"


async def test_an_existing_database_gets_the_admin_and_manager_with_the_seed_password(
    session: AsyncSession,
) -> None:
    pm = await make_user(session, GlobalRole.PM)
    project = await make_project(session, pm.id, "OLD")

    report = await ensure_core_accounts(session, PASSWORD)

    assert report == [
        "created admin@borek.test (admin)",
        "created manager@borek.test (manager)",
    ]
    users = {u.email: u for u in (await session.scalars(select(User))).all()}
    assert verify_password(PASSWORD, users["admin@borek.test"].password_hash or "")
    assert verify_password(PASSWORD, users["manager@borek.test"].password_hash or "")
    assert len(users) == 3  # no demo users and no demo projects were added
    assert [p.id for p in await session.scalars(select(Project))] == [project.id]


async def test_running_again_changes_nothing(session: AsyncSession) -> None:
    await ensure_core_accounts(session, PASSWORD)
    admin = await session.scalar(select(User).where(User.email == "admin@borek.test"))
    assert admin is not None
    admin.password_hash = hash_password("the-admin-changed-it-1")
    await session.flush()

    report = await ensure_core_accounts(session, "another-seed-password")

    assert report == ["kept admin@borek.test", "kept manager@borek.test"]
    await session.refresh(admin)
    assert verify_password("the-admin-changed-it-1", admin.password_hash or "")
    assert (await session.execute(select(func.count()).select_from(User))).scalar_one() == 2


async def test_an_account_with_that_email_is_left_alone_whatever_its_role_or_case(
    session: AsyncSession,
) -> None:
    person = await make_user(session, GlobalRole.DEVELOPER, "Admin@Borek.Test")
    report = await ensure_core_accounts(session, PASSWORD)
    assert report[0] == "kept admin@borek.test"
    await session.refresh(person)
    assert person.global_role == "developer"


async def test_a_seeded_admin_whose_email_changed_does_not_come_back(session: AsyncSession) -> None:
    await ensure_core_accounts(session, PASSWORD)
    admin = await session.scalar(select(User).where(User.email == "admin@borek.test"))
    assert admin is not None
    admin.email = "real.admin@borek.example"
    await session.flush()
    report = await ensure_core_accounts(session, PASSWORD)
    assert report[0] == "kept admin@borek.test"
    assert (await session.execute(select(func.count()).select_from(User))).scalar_one() == 2
