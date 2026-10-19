"""Project business rules. Routers check permissions; this module checks data and uses the DB."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, and_, case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.common.enums import GlobalRole, MembershipSource, ProjectRole, TaskStatus
from app.core.errors import AppError
from app.projects.models import Project, ProjectMember
from app.projects.schemas import MemberIn, ProjectCreate, ProjectUpdate, TaskSummary
from app.tasks.models import Task
from app.users.models import User


def not_found() -> AppError:
    return AppError(404, "NOT_FOUND", "Project not found.")


def version_conflict() -> AppError:
    return AppError(
        409, "VERSION_CONFLICT", "The project was changed by someone else. Reload and try again."
    )


async def get_project(session: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise not_found()
    return project


async def get_active_project(session: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await get_project(session, project_id)
    if project.archived_at is not None:
        raise AppError(409, "PROJECT_ARCHIVED", "The project is archived.")
    return project


async def _load_members(
    session: AsyncSession, project_id: uuid.UUID
) -> list[tuple[ProjectMember, User]]:
    rows = await session.execute(
        select(ProjectMember, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project_id)
        .order_by(User.name, User.email)
    )
    return [(member, user) for member, user in rows.all()]


async def list_members(
    session: AsyncSession, project_id: uuid.UUID
) -> list[tuple[ProjectMember, User]]:
    return await _load_members(session, project_id)


async def task_summaries(
    session: AsyncSession, project_ids: list[uuid.UUID]
) -> dict[uuid.UUID, TaskSummary]:
    """Counts per project in one query. Projects without tasks are absent (use `TaskSummary()`)."""
    if not project_ids:
        return {}
    today = datetime.now(UTC).date()
    done = TaskStatus.COMPLETED.value

    def count_where(condition: ColumnElement[bool]) -> ColumnElement[int]:
        return func.count(case((condition, 1)))

    rows = await session.execute(
        select(
            Task.project_id,
            func.count(Task.id),
            count_where(Task.status == done),
            count_where(Task.status == TaskStatus.IN_PROGRESS.value),
            count_where(Task.status == TaskStatus.BLOCKED.value),
            count_where(and_(Task.due_date < today, Task.status != done)),
        )
        .where(
            Task.project_id.in_(project_ids),
            Task.archived_at.is_(None),
            Task.status != TaskStatus.CANCELLED.value,
        )
        .group_by(Task.project_id)
    )
    return {
        project_id: TaskSummary(
            total=total,
            completed=completed,
            in_progress=in_progress,
            blocked=blocked,
            overdue=overdue,
            completion_percent=round(100 * completed / total) if total else 0,
        )
        for project_id, total, completed, in_progress, blocked, overdue in rows.all()
    }


async def list_projects(
    session: AsyncSession,
    user: User,
    *,
    q: str | None,
    status: str | None,
    include_archived: bool,
    page: int,
    page_size: int,
) -> tuple[list[Project], int]:
    """PMs see every project; developers only the ones they are a member of."""
    conditions: list[ColumnElement[bool]] = []
    if user.global_role != GlobalRole.PM:
        conditions.append(
            Project.id.in_(select(ProjectMember.project_id).where(ProjectMember.user_id == user.id))
        )
        include_archived = False
    if not include_archived:
        conditions.append(Project.archived_at.is_(None))
    if status:
        conditions.append(Project.status == status)
    if q:
        pattern = f"%{q.strip().replace('%', r'\%').replace('_', r'\_')}%"
        conditions.append(
            or_(Project.name.ilike(pattern, escape="\\"), Project.code.ilike(pattern, escape="\\"))
        )

    total = await session.scalar(select(func.count(Project.id)).where(*conditions)) or 0
    rows = await session.scalars(
        select(Project)
        .where(*conditions)
        .order_by(Project.code)
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    return list(rows), total


async def _check_member_users(session: AsyncSession, members: list[MemberIn]) -> None:
    ids = [m.user_id for m in members]
    if len(set(ids)) != len(ids):
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "A user can only be added once.",
            [{"field": "members", "issue": "duplicate_user", "message": "Duplicate user."}],
        )
    if not ids:
        return
    found = set(
        await session.scalars(select(User.id).where(User.id.in_(ids), User.is_active.is_(True)))
    )
    missing = [str(i) for i in ids if i not in found]
    if missing:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "Some users do not exist or are inactive.",
            [
                {"field": "members", "issue": "unknown_user", "message": f"Unknown user {i}."}
                for i in missing
            ],
        )


def _duplicate_code(code: str) -> AppError:
    return AppError(
        409,
        "DUPLICATE_CODE",
        f"A project with code {code} already exists.",
        [{"field": "code", "issue": "duplicate", "message": "This code is already used."}],
    )


async def create_project(session: AsyncSession, user: User, data: ProjectCreate) -> Project:
    await _check_member_users(session, data.members)
    existing = await session.scalar(select(Project.id).where(Project.code == data.code))
    if existing is not None:
        raise _duplicate_code(data.code)

    project = Project(
        code=data.code,
        name=data.name,
        description=data.description,
        status=data.status.value,
        start_date=data.start_date,
        target_end_date=data.target_end_date,
        created_by=user.id,
    )
    session.add(project)
    try:
        await session.flush()  # a concurrent insert of the same code fails here
    except IntegrityError:
        await session.rollback()
        raise _duplicate_code(data.code) from None
    for member in data.members:
        session.add(
            ProjectMember(
                project_id=project.id,
                user_id=member.user_id,
                project_role=member.project_role.value,
                source=MembershipSource.INVITATION.value,
                granted_by=user.id,
            )
        )
    await session.commit()
    return project


async def update_project(
    session: AsyncSession, project_id: uuid.UUID, data: ProjectUpdate
) -> Project:
    project = await get_active_project(session, project_id)
    if data.version != project.version:
        raise version_conflict()

    changes = data.model_dump(exclude={"version"}, exclude_unset=True)
    if "name" in changes and changes["name"] is None:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "The request is not valid.",
            [{"field": "name", "issue": "required", "message": "Name is required."}],
        )
    if "status" in changes and changes["status"] is None:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "The request is not valid.",
            [{"field": "status", "issue": "required", "message": "Status cannot be empty."}],
        )
    start = changes.get("start_date", project.start_date)
    end = changes.get("target_end_date", project.target_end_date)
    if start and end and end < start:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "The request is not valid.",
            [
                {
                    "field": "target_end_date",
                    "issue": "before_start",
                    "message": "target_end_date must not be before start_date.",
                }
            ],
        )

    for field, value in changes.items():
        setattr(project, field, value.value if field == "status" else value)
    try:
        await session.commit()
    except StaleDataError:
        await session.rollback()
        raise version_conflict() from None
    await session.refresh(project)  # updated_at is set by the database
    return project


async def archive_project(session: AsyncSession, project_id: uuid.UUID) -> None:
    """Soft delete: hidden from lists, data kept. Archiving twice is harmless."""
    project = await get_project(session, project_id)
    if project.archived_at is None:
        project.archived_at = datetime.now(UTC)
        await session.commit()


async def add_member(
    session: AsyncSession, project: Project, granted_by: User, data: MemberIn
) -> tuple[ProjectMember, User]:
    await _check_member_users(session, [data])
    existing = await session.scalar(
        select(ProjectMember.id).where(
            ProjectMember.project_id == project.id, ProjectMember.user_id == data.user_id
        )
    )
    if existing is not None:
        raise AppError(409, "ALREADY_MEMBER", "The user is already a member of this project.")
    member = ProjectMember(
        project_id=project.id,
        user_id=data.user_id,
        project_role=data.project_role.value,
        source=MembershipSource.INVITATION.value,
        granted_by=granted_by.id,
    )
    session.add(member)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise AppError(
            409, "ALREADY_MEMBER", "The user is already a member of this project."
        ) from None
    user = await session.get(User, data.user_id)
    assert user is not None
    return member, user


async def _get_member(
    session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID
) -> ProjectMember:
    member = await session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user_id
        )
    )
    if member is None:
        raise AppError(404, "NOT_FOUND", "Member not found.")
    return member


async def change_member_role(
    session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID, role: ProjectRole
) -> tuple[ProjectMember, User]:
    member = await _get_member(session, project_id, user_id)
    member.project_role = role.value
    await session.commit()
    user = await session.get(User, user_id)
    assert user is not None
    return member, user


async def remove_member(session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Remove the user and unassign their tasks here, so no task keeps a non-member assignee."""
    member = await _get_member(session, project_id, user_id)
    await session.execute(
        update(Task)
        .where(Task.project_id == project_id, Task.assignee_id == user_id)
        .values(assignee_id=None, version=Task.version + 1)
    )
    await session.delete(member)
    await session.commit()
