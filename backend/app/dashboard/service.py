"""Dashboard queries. Every number comes from the same task rows as the lists and the board."""

import uuid

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole, ProjectStatus, StatusCategory
from app.dashboard.schemas import (
    AttentionList,
    MemberCounts,
    MyDashboard,
    PmDashboard,
    ProjectCard,
)
from app.projects import service as project_service
from app.projects.models import Project, ProjectMember
from app.projects.schemas import TaskSummary
from app.tasks import service as task_service
from app.tasks.models import Task, WorkflowStatus
from app.tasks.schemas import UserBrief
from app.users.models import User


def _total(summaries: list[TaskSummary]) -> TaskSummary:
    return project_service.make_summary(
        sum(s.total for s in summaries),
        sum(s.completed for s in summaries),
        sum(s.in_progress for s in summaries),
        sum(s.blocked for s in summaries),
        sum(s.overdue for s in summaries),
    )


def _card(
    project: Project, summary: TaskSummary | None, members: list[MemberCounts] | None = None
) -> ProjectCard:
    return ProjectCard(
        id=project.id,
        code=project.code,
        name=project.name,
        status=project.status,
        start_date=project.start_date,
        target_end_date=project.target_end_date,
        tasks=summary or TaskSummary(),
        members=members or [],
    )


async def _attention(
    session: AsyncSession,
    limit: int,
    *,
    category: StatusCategory | None = None,
    overdue: bool = False,
    assignee_id: uuid.UUID | None = None,
    scope: ColumnElement[bool] | None = None,
) -> AttentionList:
    filters = task_service.TaskFilters(
        categories=[category] if category else None, overdue=overdue, assignee_id=assignee_id
    )
    items, total = await task_service.list_tasks(
        session,
        filters,
        sort="due_date" if overdue else "updated_at",
        page=1,
        page_size=limit,
        scope=scope,
    )
    return AttentionList(total=total, items=items)


async def pm_dashboard(session: AsyncSession, limit: int) -> PmDashboard:
    projects = list(
        await session.scalars(
            select(Project).where(Project.archived_at.is_(None)).order_by(Project.code)
        )
    )
    summaries = await project_service.task_summaries(session, [p.id for p in projects])
    return PmDashboard(
        active_projects=sum(p.status == ProjectStatus.ACTIVE.value for p in projects),
        projects_total=len(projects),
        summary=_total(list(summaries.values())),
        projects=[_card(p, summaries.get(p.id)) for p in projects],
        blocked=await _attention(session, limit, category=StatusCategory.BLOCKED),
        overdue=await _attention(session, limit, overdue=True),
    )


async def my_dashboard(session: AsyncSession, user: User, limit: int) -> MyDashboard:
    scope = None if user.global_role == GlobalRole.PM else task_service.scope_for_developer(user)
    mine = [
        Task.assignee_id == user.id,
        Task.archived_at.is_(None),
        Project.archived_at.is_(None),
    ]
    if scope is not None:
        mine.append(scope)
    counts = (
        await session.execute(
            select(*project_service.summary_columns())
            .join(WorkflowStatus, WorkflowStatus.id == Task.status_id)
            .join(Project, Project.id == Task.project_id)
            .where(*mine)
        )
    ).one()

    projects = list(
        await session.scalars(
            select(Project)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(ProjectMember.user_id == user.id, Project.archived_at.is_(None))
            .order_by(Project.code)
        )
    )
    ids = [p.id for p in projects]
    summaries = await project_service.task_summaries(session, ids)
    members = await _member_counts(session, ids)
    return MyDashboard(
        summary=project_service.make_summary(*counts),
        projects=[_card(p, summaries.get(p.id), members.get(p.id)) for p in projects],
        blocked=await _attention(
            session, limit, category=StatusCategory.BLOCKED, assignee_id=user.id, scope=scope
        ),
        overdue=await _attention(session, limit, overdue=True, assignee_id=user.id, scope=scope),
    )


async def _member_counts(
    session: AsyncSession, project_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[MemberCounts]]:
    """Per project: every member with the counts of the tasks assigned to them there."""
    if not project_ids:
        return {}
    rows = await session.execute(
        select(Task.project_id, Task.assignee_id, *project_service.summary_columns())
        .join(WorkflowStatus, WorkflowStatus.id == Task.status_id)
        .where(
            Task.project_id.in_(project_ids),
            Task.assignee_id.is_not(None),
            Task.archived_at.is_(None),
        )
        .group_by(Task.project_id, Task.assignee_id)
    )
    counts = {(pid, uid): project_service.make_summary(*c) for pid, uid, *c in rows.all()}
    people = await session.execute(
        select(ProjectMember, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id.in_(project_ids))
        .order_by(User.name)
    )
    result: dict[uuid.UUID, list[MemberCounts]] = {}
    for member, person in people.all():
        result.setdefault(member.project_id, []).append(
            MemberCounts(
                user=UserBrief(id=person.id, name=person.name, email=person.email),
                project_role=member.project_role,
                tasks=counts.get((member.project_id, person.id), TaskSummary()),
            )
        )
    return result
