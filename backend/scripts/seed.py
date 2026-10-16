"""Seed demo data: 1 PM, 3 developers, 3 projects, and tasks covering every demo case.

Run from the backend folder:  python -m scripts.seed          (adds data to an empty database)
                              python -m scripts.seed --reset  (wipes the data tables first)
"""

import argparse
import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import (
    GlobalRole,
    MembershipSource,
    ProjectRole,
    ProjectStatus,
    TaskPriority,
    TaskStatus,
)
from app.core.config import get_settings
from app.core.database import get_engine, get_sessionmaker
from app.projects.models import Project, ProjectMember
from app.tasks.models import Task
from app.users.models import User

# Fixed IDs so the dev user picker (X-Dev-User-Id) stays stable across resets.
PM_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
DEV1_ID = uuid.UUID("00000000-0000-4000-8000-000000000011")
DEV2_ID = uuid.UUID("00000000-0000-4000-8000-000000000012")
DEV3_ID = uuid.UUID("00000000-0000-4000-8000-000000000013")

USERS = [
    (PM_ID, "Test PM", "pm@borek.test", GlobalRole.PM),
    (DEV1_ID, "Dev One", "dev1@borek.test", GlobalRole.DEVELOPER),
    (DEV2_ID, "Dev Two", "dev2@borek.test", GlobalRole.DEVELOPER),
    (DEV3_ID, "Dev Three", "dev3@borek.test", GlobalRole.DEVELOPER),
]

# (code, name, status, start offset days, end offset days, members: {user_id: role})
PROJECTS = [
    (
        "ALPHA",
        "Alpha Platform",
        ProjectStatus.ACTIVE,
        -60,
        45,
        {DEV1_ID: ProjectRole.PROJECT_LEAD, DEV2_ID: ProjectRole.DEVELOPER},
    ),
    (
        "BETA",
        "Beta Portal",
        ProjectStatus.ACTIVE,
        -30,
        90,
        {DEV2_ID: ProjectRole.PROJECT_LEAD, DEV3_ID: ProjectRole.DEVELOPER},
    ),
    (
        "GAMMA",
        "Gamma Migration",
        ProjectStatus.PLANNED,
        15,
        120,
        {DEV3_ID: ProjectRole.PROJECT_LEAD},
    ),
]

# (project code, title, status, priority, assignee, due offset days, progress, blocked reason)
TASKS = [
    (
        "ALPHA",
        "Set up CI pipeline",
        TaskStatus.COMPLETED,
        TaskPriority.HIGH,
        DEV1_ID,
        -20,
        100,
        None,
    ),
    (
        "ALPHA",
        "Design database schema",
        TaskStatus.COMPLETED,
        TaskPriority.CRITICAL,
        DEV1_ID,
        -30,
        100,
        None,
    ),
    (
        "ALPHA",
        "Build login screen",
        TaskStatus.IN_PROGRESS,
        TaskPriority.HIGH,
        DEV2_ID,
        7,
        60,
        None,
    ),
    (
        "ALPHA",
        "Implement report export",
        TaskStatus.OPEN,
        TaskPriority.MEDIUM,
        DEV2_ID,
        14,
        0,
        None,
    ),
    (
        "ALPHA",
        "Fix date formatting bug",
        TaskStatus.IN_PROGRESS,
        TaskPriority.HIGH,
        DEV1_ID,
        -3,
        40,
        None,
    ),  # overdue
    (
        "ALPHA",
        "Integrate payment API",
        TaskStatus.BLOCKED,
        TaskPriority.CRITICAL,
        DEV1_ID,
        5,
        30,
        "Waiting for API credentials from the client",
    ),
    (
        "ALPHA",
        "Write user documentation",
        TaskStatus.OPEN,
        TaskPriority.LOW,
        None,
        30,
        0,
        None,
    ),  # unassigned
    (
        "ALPHA",
        "Review security checklist",
        TaskStatus.IN_REVIEW,
        TaskPriority.MEDIUM,
        DEV2_ID,
        2,
        90,
        None,
    ),
    (
        "BETA",
        "Create landing page",
        TaskStatus.IN_PROGRESS,
        TaskPriority.MEDIUM,
        DEV3_ID,
        10,
        50,
        None,
    ),
    (
        "BETA",
        "Customer data import",
        TaskStatus.OPEN,
        TaskPriority.HIGH,
        DEV2_ID,
        -7,
        0,
        None,
    ),  # overdue
    (
        "BETA",
        "Set up monitoring",
        TaskStatus.BLOCKED,
        TaskPriority.HIGH,
        DEV3_ID,
        12,
        20,
        "Azure subscription not yet available",
    ),
    (
        "BETA",
        "Accessibility audit",
        TaskStatus.OPEN,
        TaskPriority.LOW,
        None,
        None,
        0,
        None,
    ),  # unassigned, no due date
    ("BETA", "Old prototype cleanup", TaskStatus.CANCELLED, TaskPriority.LOW, None, -10, 0, None),
    (
        "BETA",
        "Finalize navigation",
        TaskStatus.COMPLETED,
        TaskPriority.MEDIUM,
        DEV3_ID,
        -5,
        100,
        None,
    ),
    (
        "GAMMA",
        "Inventory legacy systems",
        TaskStatus.OPEN,
        TaskPriority.MEDIUM,
        DEV3_ID,
        20,
        0,
        None,
    ),
    ("GAMMA", "Draft migration plan", TaskStatus.OPEN, TaskPriority.HIGH, None, 25, 0, None),
]


def check_environment() -> None:
    if get_settings().environment == "production":
        raise SystemExit("Refusing to seed demo data when ENVIRONMENT=production.")


async def reset(session: AsyncSession) -> None:
    await session.execute(
        text("TRUNCATE tasks, project_members, projects, users RESTART IDENTITY CASCADE")
    )


async def seed(session: AsyncSession, today: date | None = None) -> None:
    """Insert the demo data. Fails if users already exist (use reset first)."""
    today = today or datetime.now(UTC).date()
    if (await session.execute(select(User.id).limit(1))).first() is not None:
        raise SystemExit("The database already has data. Use --reset to replace it.")

    session.add_all(
        User(id=uid, name=name, email=email, global_role=role.value)
        for uid, name, email, role in USERS
    )
    await session.flush()

    projects: dict[str, Project] = {}
    for code, name, status, start, end, members in PROJECTS:
        project = Project(
            code=code,
            name=name,
            description=f"Demo project {name}.",
            status=status.value,
            start_date=today + timedelta(days=start),
            target_end_date=today + timedelta(days=end),
            created_by=PM_ID,
        )
        session.add(project)
        await session.flush()
        projects[code] = project
        for user_id, role in members.items():
            session.add(
                ProjectMember(
                    project_id=project.id,
                    user_id=user_id,
                    project_role=role.value,
                    source=MembershipSource.INVITATION.value,
                    granted_by=PM_ID,
                )
            )

    now = datetime.now(UTC)
    for code, title, task_status, priority, assignee, due, progress, reason in TASKS:
        project = projects[code]
        project.task_counter += 1
        session.add(
            Task(
                project_id=project.id,
                key=f"TSK-{project.task_counter:03d}",
                title=title,
                status=task_status.value,
                priority=priority.value,
                assignee_id=assignee,
                due_date=None if due is None else today + timedelta(days=due),
                progress=progress,
                blocked_reason=reason,
                created_by=PM_ID,
                completed_at=now if task_status is TaskStatus.COMPLETED else None,
            )
        )
    await session.flush()


async def main(do_reset: bool) -> None:
    check_environment()
    async with get_sessionmaker()() as session, session.begin():
        if do_reset:
            await reset(session)
        await seed(session)
    await get_engine().dispose()
    print(f"Seeded {len(USERS)} users, {len(PROJECTS)} projects, {len(TASKS)} tasks.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo data.")
    parser.add_argument("--reset", action="store_true", help="wipe all data tables first")
    asyncio.run(main(parser.parse_args().reset))
