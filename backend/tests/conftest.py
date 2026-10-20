"""Test database fixtures.

Tests run against a separate database (<name>_test) on the same Postgres server as DATABASE_URL.
It is created if missing and built by running the real Alembic migrations.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from alembic.config import Config
from app.common.enums import GlobalRole
from app.core.config import get_settings
from app.projects.models import Project
from app.tasks import statuses
from app.tasks.models import Task, WorkflowStatus
from app.users.models import User

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _test_url() -> str:
    url = make_url(get_settings().database_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


async def _create_database_if_missing(url_text: str) -> None:
    url = make_url(url_text)
    connection = await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database="postgres",
    )
    try:
        exists = await connection.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", url.database
        )
        if not exists:
            await connection.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await connection.close()


def alembic_config(url_text: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url_text)
    return config


@pytest.fixture(scope="session")
def test_db_url() -> str:
    """Create the test database and bring it to the latest migration."""
    url_text = _test_url()
    asyncio.run(_create_database_if_missing(url_text))
    config = alembic_config(url_text)
    command.downgrade(config, "base")  # start from a clean schema every run
    command.upgrade(config, "head")
    return url_text


@pytest_asyncio.fixture
async def session(test_db_url: str) -> AsyncIterator[AsyncSession]:
    """A session on an empty test database (all data tables truncated first)."""
    engine = create_async_engine(test_db_url, poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE tasks, project_statuses, project_members, projects, users "
                "RESTART IDENTITY CASCADE"
            )
        )
    async with async_sessionmaker(engine, expire_on_commit=False)() as db_session:
        yield db_session
    await engine.dispose()


async def make_user(
    session: AsyncSession, role: GlobalRole = GlobalRole.DEVELOPER, email: str | None = None
) -> User:
    user = User(
        name="Test User",
        email=email or f"{uuid.uuid4().hex[:8]}@test.example",
        global_role=role.value,
    )
    session.add(user)
    await session.flush()
    return user


async def make_project(session: AsyncSession, created_by: uuid.UUID, code: str = "PRJ") -> Project:
    project = Project(code=code, name="Test project", created_by=created_by)
    session.add(project)
    await session.flush()
    await statuses.create_defaults(session, project.id)  # like POST /projects does
    return project


async def status_by_name(session: AsyncSession, project_id: uuid.UUID, name: str) -> WorkflowStatus:
    status = await session.scalar(
        select(WorkflowStatus).where(
            WorkflowStatus.project_id == project_id, WorkflowStatus.name == name
        )
    )
    assert status is not None, name
    return status


async def make_task(
    session: AsyncSession,
    project: Project,
    created_by: uuid.UUID,
    *,
    status: str = "To do",
    title: str = "A task",
    **values: Any,
) -> Task:
    """Insert a task directly (bypassing the API) with the next key number."""
    project.task_counter += 1
    status_row = await status_by_name(session, project.id, status)
    values.setdefault("key", f"{project.code}-{project.task_counter}")
    task = Task(
        project_id=project.id,
        title=title,
        status_id=status_row.id,
        created_by=created_by,
        **values,
    )
    session.add(task)
    await session.flush()
    return task
