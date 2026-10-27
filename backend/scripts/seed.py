"""Seed demo data: 1 PM, 3 developers, 4 projects, and tasks covering every demo case.

Run from the backend folder:  python -m scripts.seed          (adds data to an empty database)
                              python -m scripts.seed --reset  (wipes the data tables first)

Production-like hosts (AUTH_MODE=local) have no user picker, so the seed users need a password:
set SEED_USER_PASSWORD (12+ characters, shared by the seed users) and the users can sign in with
their @borek.test email. Seeding is refused when ENVIRONMENT=production unless --allow-production
is given, and --reset is never allowed there. --if-empty makes it safe to run on every start.
"""

import argparse
import asyncio
import os
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password
from app.common.enums import (
    GlobalRole,
    MembershipSource,
    ProjectRole,
    ProjectStatus,
    TaskPriority,
)
from app.core.config import get_settings
from app.core.database import get_engine, get_sessionmaker
from app.projects.models import Project, ProjectMember
from app.tasks import statuses
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
    (
        "DELTA",
        "Delta Customer Portal",
        ProjectStatus.ACTIVE,
        -45,
        60,
        {
            DEV1_ID: ProjectRole.DEVELOPER,
            DEV2_ID: ProjectRole.PROJECT_LEAD,
            DEV3_ID: ProjectRole.DEVELOPER,
        },
    ),
]

# (project code, title, status name, priority, assignee, due offset days, blocked reason)
TASKS = [
    (
        "ALPHA",
        "Set up CI pipeline",
        "Done",
        TaskPriority.HIGH,
        DEV1_ID,
        -20,
        None,
    ),
    (
        "ALPHA",
        "Design database schema",
        "Done",
        TaskPriority.CRITICAL,
        DEV1_ID,
        -30,
        None,
    ),
    (
        "ALPHA",
        "Build login screen",
        "In progress",
        TaskPriority.HIGH,
        DEV2_ID,
        7,
        None,
    ),
    (
        "ALPHA",
        "Implement report export",
        "To do",
        TaskPriority.MEDIUM,
        DEV2_ID,
        14,
        None,
    ),
    (
        "ALPHA",
        "Fix date formatting bug",
        "In progress",
        TaskPriority.HIGH,
        DEV1_ID,
        -3,
        None,
    ),  # overdue
    (
        "ALPHA",
        "Integrate payment API",
        "Blocked",
        TaskPriority.CRITICAL,
        DEV1_ID,
        5,
        "Waiting for API credentials from the client",
    ),
    (
        "ALPHA",
        "Write user documentation",
        "To do",
        TaskPriority.LOW,
        None,
        30,
        None,
    ),  # unassigned
    (
        "ALPHA",
        "Review security checklist",
        "Code review",
        TaskPriority.MEDIUM,
        DEV2_ID,
        2,
        None,
    ),
    (
        "BETA",
        "Create landing page",
        "In progress",
        TaskPriority.MEDIUM,
        DEV3_ID,
        10,
        None,
    ),
    (
        "BETA",
        "Customer data import",
        "To do",
        TaskPriority.HIGH,
        DEV2_ID,
        -7,
        None,
    ),  # overdue
    (
        "BETA",
        "Set up monitoring",
        "Blocked",
        TaskPriority.HIGH,
        DEV3_ID,
        12,
        "Azure subscription not yet available",
    ),
    (
        "BETA",
        "Accessibility audit",
        "To do",
        TaskPriority.LOW,
        None,
        None,
        None,
    ),  # unassigned, no due date
    ("BETA", "Old prototype cleanup", "Backlog", TaskPriority.LOW, None, -10, None),  # archived
    (
        "BETA",
        "Finalize navigation",
        "Done",
        TaskPriority.MEDIUM,
        DEV3_ID,
        -5,
        None,
    ),
    (
        "GAMMA",
        "Inventory legacy systems",
        "To do",
        TaskPriority.MEDIUM,
        DEV3_ID,
        20,
        None,
    ),
    ("GAMMA", "Draft migration plan", "To do", TaskPriority.HIGH, None, 25, None),
]


# Labels for a few tasks, so label filters have something to show.
LABELS = {
    "Fix date formatting bug": ["bug"],
    "Integrate payment API": ["integration", "backend"],
    "Build login screen": ["frontend"],
    "Set up monitoring": ["devops"],
}
ARCHIVED_TITLES = {"Old prototype cleanup"}


MIN_PASSWORD_LENGTH = 12


def check_environment(allow_production: bool = False, do_reset: bool = False) -> None:
    if get_settings().environment != "production":
        return
    if do_reset:
        raise SystemExit("Refusing to wipe data when ENVIRONMENT=production.")
    if not allow_production:
        raise SystemExit(
            "Refusing to seed demo data when ENVIRONMENT=production (use --allow-production)."
        )


def read_seed_password() -> str | None:
    """The shared password of the seed users (None = no password, dev picker only)."""
    password = os.environ.get("SEED_USER_PASSWORD", "")
    if not password:
        return None
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"SEED_USER_PASSWORD needs at least {MIN_PASSWORD_LENGTH} characters.")
    return password


async def reset(session: AsyncSession) -> None:
    await session.execute(
        text(
            "TRUNCATE tasks, project_statuses, project_members, projects, users "
            "RESTART IDENTITY CASCADE"
        )
    )


async def seed(
    session: AsyncSession, today: date | None = None, password: str | None = None
) -> None:
    """Insert the demo data. Fails if projects already exist (use reset first)."""
    today = today or datetime.now(UTC).date()
    if (await session.execute(select(Project.id).limit(1))).first() is not None:
        raise SystemExit("The database already has data. Use --reset to replace it.")

    password_hash = hash_password(password) if password else None
    session.add_all(
        User(id=uid, name=name, email=email, global_role=role.value, password_hash=password_hash)
        for uid, name, email, role in USERS
    )
    await session.flush()

    projects: dict[str, Project] = {}
    status_ids: dict[str, dict[str, uuid.UUID]] = {}
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
        status_ids[code] = {
            status.name: status.id for status in await statuses.create_defaults(session, project.id)
        }
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
    for code, title, status_name, priority, assignee, due, reason in TASKS:
        project = projects[code]
        project.task_counter += 1
        session.add(
            Task(
                project_id=project.id,
                key=f"{project.code}-{project.task_counter}",
                title=title,
                status_id=status_ids[code][status_name],
                labels=LABELS.get(title, []),
                priority=priority.value,
                assignee_id=assignee,
                due_date=None if due is None else today + timedelta(days=due),
                blocked_reason=reason,
                blocked_at=now if reason else None,
                created_by=PM_ID,
                completed_at=now if status_name == "Done" else None,
                archived_at=now if title in ARCHIVED_TITLES else None,
            )
        )
    await session.flush()


async def main(do_reset: bool, allow_production: bool, if_empty: bool) -> None:
    check_environment(allow_production, do_reset)
    password = read_seed_password()
    if get_settings().environment == "production" and password is None:
        raise SystemExit("SEED_USER_PASSWORD is required in production (no user picker there).")
    async with get_sessionmaker()() as session, session.begin():
        if do_reset:
            await reset(session)
        elif if_empty and (await session.execute(select(Project.id).limit(1))).first():
            print("Database already has data; seed skipped.")
            await get_engine().dispose()
            return
        await seed(session, password=password)
    await get_engine().dispose()
    print(f"Seeded {len(USERS)} users, {len(PROJECTS)} projects, {len(TASKS)} tasks.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo data.")
    parser.add_argument("--reset", action="store_true", help="wipe all data tables first")
    parser.add_argument(
        "--allow-production", action="store_true", help="allow seeding when ENVIRONMENT=production"
    )
    parser.add_argument(
        "--if-empty", action="store_true", help="do nothing (success) when data already exists"
    )
    args = parser.parse_args()
    asyncio.run(main(args.reset, args.allow_production, args.if_empty))
