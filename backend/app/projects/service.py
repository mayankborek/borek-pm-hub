"""Project business rules. Routers check permissions; this module checks data and uses the DB."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, and_, case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.audit.service import record_audit
from app.auth.permissions import (
    Action,
    can,
    may_lead_projects,
    require,
    sees_all_projects,
    works_on_tasks_condition,
)
from app.common.enums import (
    MembershipSource,
    OrganisationType,
    ProjectRole,
    ProjectStatus,
    StatusCategory,
)
from app.common.validation import like_escape
from app.core.errors import AppError
from app.organisations.models import Organisation
from app.organisations.schemas import OrganisationBrief
from app.projects.membership import project_access, visible_project_ids
from app.projects.models import Project, ProjectMember
from app.projects.schemas import MemberIn, ProjectCreate, ProjectUpdate, TaskSummary
from app.tasks import activity, statuses
from app.tasks.models import Task, WorkflowStatus
from app.users.models import User


def _text(value: uuid.UUID | None) -> str | None:
    return None if value is None else str(value)


def not_found() -> AppError:
    return AppError(404, "NOT_FOUND", "Project not found.")


def version_conflict() -> AppError:
    return AppError(
        409, "VERSION_CONFLICT", "The project was changed by someone else. Reload and try again."
    )


async def client_organisations(
    session: AsyncSession, projects: list[Project]
) -> dict[uuid.UUID | None, OrganisationBrief]:
    """The customers of these projects, by id, in one query."""
    ids = {p.client_organisation_id for p in projects if p.client_organisation_id}
    if not ids:
        return {}
    rows = await session.execute(
        select(Organisation.id, Organisation.name).where(Organisation.id.in_(ids))
    )
    return {row.id: OrganisationBrief(id=row.id, name=row.name) for row in rows.all()}


async def _check_client_organisation(session: AsyncSession, organisation_id: uuid.UUID) -> None:
    organisation = await session.get(Organisation, organisation_id)
    if (
        organisation is None
        or organisation.archived_at is not None
        or organisation.type != OrganisationType.CLIENT.value
    ):
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "The request is not valid.",
            [
                {
                    "field": "client_organisation_id",
                    "issue": "unknown_client",
                    "message": "This is not an active client organisation.",
                }
            ],
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


def ensure_writable(project: Project) -> None:
    """Archived and cancelled projects are read-only. A cancelled one opens again when the PM
    sets another status (PATCH /projects/{id} stays allowed for that)."""
    if project.archived_at is not None:
        raise AppError(409, "PROJECT_ARCHIVED", "The project is archived.")
    if project.status == ProjectStatus.CANCELLED.value:
        raise AppError(
            409,
            "PROJECT_CANCELLED",
            "The project is cancelled. Set it to another status to make changes.",
        )


async def get_writable_project(session: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await get_project(session, project_id)
    ensure_writable(project)
    return project


async def authorize(
    session: AsyncSession,
    user: User,
    project_id: uuid.UUID,
    action: Action,
    *,
    writable: bool = False,
) -> Project:
    """Load the project and apply `action`: people who cannot see the project get 404. With
    `writable`, archived and cancelled projects are refused too."""
    project = await get_project(session, project_id)
    access = await project_access(session, user, project)
    require(user, action, access.resource(project_id))
    if writable:
        ensure_writable(project)
    return project


async def allowed_in(session: AsyncSession, user: User, project: Project, action: Action) -> bool:
    access = await project_access(session, user, project)
    return can(user, action, access.resource(project.id))


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


def summary_columns() -> tuple[ColumnElement[int], ...]:
    """Aggregate columns (total, completed, in progress, blocked, overdue) over tasks joined with
    their status. Callers add the joins, filters and grouping; `make_summary` reads the row."""
    today = datetime.now(UTC).date()
    done = StatusCategory.DONE.value

    def count_where(condition: ColumnElement[bool]) -> ColumnElement[int]:
        return func.count(case((condition, 1)))

    return (
        func.count(Task.id),
        count_where(WorkflowStatus.category == done),
        count_where(WorkflowStatus.category == StatusCategory.IN_PROGRESS.value),
        count_where(WorkflowStatus.category == StatusCategory.BLOCKED.value),
        count_where(and_(Task.due_date < today, WorkflowStatus.category != done)),
    )


def make_summary(
    total: int, completed: int, in_progress: int, blocked: int, overdue: int
) -> TaskSummary:
    return TaskSummary(
        total=total,
        completed=completed,
        in_progress=in_progress,
        blocked=blocked,
        overdue=overdue,
        completion_percent=round(100 * completed / total) if total else 0,
    )


async def task_summaries(
    session: AsyncSession, project_ids: list[uuid.UUID]
) -> dict[uuid.UUID, TaskSummary]:
    """Counts per project in one query. Projects without tasks are absent (use `TaskSummary()`)."""
    if not project_ids:
        return {}
    rows = await session.execute(
        select(Task.project_id, *summary_columns())
        .join(WorkflowStatus, WorkflowStatus.id == Task.status_id)
        .where(Task.project_id.in_(project_ids), Task.archived_at.is_(None))
        .group_by(Task.project_id)
    )
    return {project_id: make_summary(*counts) for project_id, *counts in rows.all()}


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
    """Managers see every project; everyone else the ones they are a member of. With
    `include_archived` a PM also gets the archived projects they led or archived."""
    conditions: list[ColumnElement[bool]] = []
    if not sees_all_projects(user):
        active_mine = Project.id.in_(visible_project_ids(user))
        if include_archived and may_lead_projects(user):
            led = Project.id.in_(
                select(ProjectMember.project_id).where(
                    ProjectMember.user_id == user.id,
                    ProjectMember.project_role == ProjectRole.PROJECT_LEAD.value,
                )
            )
            conditions.append(or_(active_mine, led, Project.archived_by == user.id))
        else:
            conditions.append(active_mine)
    elif not include_archived:
        conditions.append(Project.archived_at.is_(None))
    if status:
        conditions.append(Project.status == status)
    if q:
        pattern = f"%{like_escape(q.strip())}%"
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
        await session.scalars(
            select(User.id).where(
                User.id.in_(ids), User.is_active.is_(True), works_on_tasks_condition()
            )
        )
    )
    missing = [str(i) for i in ids if i not in found]
    if missing:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "Some users do not exist, are inactive or cannot work on projects.",
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
    if data.client_organisation_id:
        await _check_client_organisation(session, data.client_organisation_id)
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
        client_organisation_id=data.client_organisation_id,
        created_by=user.id,
    )
    session.add(project)
    try:
        await session.flush()  # a concurrent insert of the same code fails here
    except IntegrityError:
        await session.rollback()
        raise _duplicate_code(data.code) from None
    await statuses.create_defaults(session, project.id)
    # The creator always leads the project, even when also listed as a plain member.
    roles = {member.user_id: member.project_role for member in data.members}
    roles[user.id] = ProjectRole.PROJECT_LEAD
    for user_id, role in roles.items():
        session.add(
            ProjectMember(
                project_id=project.id,
                user_id=user_id,
                project_role=role.value,
                source=MembershipSource.INVITATION.value,
                granted_by=user.id,
            )
        )
    record_audit(
        session,
        user,
        "project.created",
        "project",
        project.id,
        project_id=project.id,
        after={
            "code": project.code,
            "name": project.name,
            "members": {str(user_id): role.value for user_id, role in roles.items()},
        },
    )
    await session.commit()
    return project


async def update_project(
    session: AsyncSession, project_id: uuid.UUID, data: ProjectUpdate, actor: User
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

    new_client = changes.get("client_organisation_id")
    if new_client and new_client != project.client_organisation_id:
        await _check_client_organisation(session, new_client)
    if (
        "client_organisation_id" in changes and new_client != project.client_organisation_id
    ):  # decides which account managers see the project, so it is on the record
        record_audit(
            session,
            actor,
            "project.client_changed",
            "project",
            project.id,
            project_id=project.id,
            before={"client_organisation_id": _text(project.client_organisation_id)},
            after={"client_organisation_id": _text(new_client)},
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


async def archive_project(session: AsyncSession, project_id: uuid.UUID, actor: User) -> None:
    """Soft delete: hidden from lists, data kept. Archiving twice is harmless and keeps who
    archived it first."""
    project = await get_project(session, project_id)
    if project.archived_at is None:
        project.archived_at = datetime.now(UTC)
        project.archived_by = actor.id
        record_audit(
            session, actor, "project.archived", "project", project.id, project_id=project.id
        )
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
    record_audit(
        session,
        granted_by,
        "member.added",
        "user",
        data.user_id,
        project_id=project.id,
        after={"project_role": data.project_role.value},
    )
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


async def _ensure_another_lead(session: AsyncSession, member: ProjectMember) -> None:
    """A project always keeps a lead who can act. Deactivated people and people whose role no
    longer works on projects do not count. The project row is locked first, so two changes at
    the same moment are handled one after the other."""
    if member.project_role != ProjectRole.PROJECT_LEAD.value:
        return
    await session.execute(
        select(Project.id).where(Project.id == member.project_id).with_for_update()
    )
    others = await session.scalar(
        select(func.count(ProjectMember.id))
        .join(User, User.id == ProjectMember.user_id)
        .where(
            ProjectMember.project_id == member.project_id,
            ProjectMember.project_role == ProjectRole.PROJECT_LEAD.value,
            ProjectMember.id != member.id,
            User.is_active.is_(True),
            works_on_tasks_condition(),
        )
    )
    if not others:
        raise AppError(
            409,
            "LAST_PROJECT_LEAD",
            "A project needs at least one project lead. Make someone else lead first.",
        )


async def change_member_role(
    session: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    role: ProjectRole,
    actor: User,
) -> tuple[ProjectMember, User]:
    member = await _get_member(session, project_id, user_id)
    if role != ProjectRole.PROJECT_LEAD:
        await _ensure_another_lead(session, member)
    if member.project_role != role.value:
        record_audit(
            session,
            actor,
            "member.role_changed",
            "user",
            user_id,
            project_id=project_id,
            before={"project_role": member.project_role},
            after={"project_role": role.value},
        )
    member.project_role = role.value
    await session.commit()
    user = await session.get(User, user_id)
    assert user is not None
    return member, user


async def remove_member(
    session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID, actor: User
) -> None:
    """Remove the user and unassign their tasks here, so no task keeps a non-member assignee.
    Each unassigned task gets a history row."""
    member = await _get_member(session, project_id, user_id)
    await _ensure_another_lead(session, member)
    name = await session.scalar(select(User.name).where(User.id == user_id))
    task_ids = await session.scalars(
        select(Task.id).where(Task.project_id == project_id, Task.assignee_id == user_id)
    )
    for task_id in task_ids:
        activity.record(session, task_id, actor.id, "updated", {"assignee": [name, None]})
    await session.execute(
        update(Task)
        .where(Task.project_id == project_id, Task.assignee_id == user_id)
        .values(assignee_id=None, version=Task.version + 1)
    )
    record_audit(
        session,
        actor,
        "member.removed",
        "user",
        user_id,
        project_id=project_id,
        before={"project_role": member.project_role},
    )
    await session.delete(member)
    await session.commit()
