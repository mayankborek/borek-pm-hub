"""Task figures for the project Overview (PM design spec 19.11.2026, page 4)."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import StatusCategory, TaskPriority
from app.manager import service as manager_service
from app.projects.models import ProjectMember
from app.tasks.models import Task, WorkflowStatus
from app.tasks.schemas import PriorityCount, StatusBrief, StatusCount, TaskStatsOut
from app.users.models import User

PRIORITY_ORDER = (
    TaskPriority.HIGHEST,
    TaskPriority.HIGH,
    TaskPriority.MEDIUM,
    TaskPriority.LOW,
    TaskPriority.LOWEST,
)


async def task_stats(session: AsyncSession, project_id: uuid.UUID) -> TaskStatsOut:
    today = datetime.now(UTC).date()
    sunday = today + timedelta(days=6 - today.weekday())
    active = and_(Task.project_id == project_id, Task.archived_at.is_(None))
    is_open = WorkflowStatus.category != StatusCategory.DONE.value

    statuses = (
        await session.scalars(
            select(WorkflowStatus)
            .where(WorkflowStatus.project_id == project_id)
            .order_by(WorkflowStatus.position)
        )
    ).all()
    status_rows = await session.execute(
        select(Task.status_id, func.count(Task.id)).where(active).group_by(Task.status_id)
    )
    per_status: dict[uuid.UUID, int] = {row[0]: row[1] for row in status_rows}
    priority_rows = await session.execute(
        select(Task.priority, func.count(Task.id)).where(active).group_by(Task.priority)
    )
    per_priority: dict[str, int] = {row[0]: row[1] for row in priority_rows}
    due_this_week, overdue = (
        await session.execute(
            select(
                func.count(case((and_(Task.due_date >= today, Task.due_date <= sunday), 1))),
                func.count(case((Task.due_date < today, 1))),
            )
            .join(WorkflowStatus, WorkflowStatus.id == Task.status_id)
            .where(active, is_open)
        )
    ).one()
    team_members, team_functions = (
        await session.execute(
            select(
                func.count(ProjectMember.id),
                func.count(func.distinct(func.lower(func.nullif(func.trim(User.job_title), "")))),
            )
            .join(User, User.id == ProjectMember.user_id)
            .where(ProjectMember.project_id == project_id, User.is_active.is_(True))
        )
    ).one()

    by_status = [
        StatusCount(
            status=StatusBrief(id=s.id, name=s.name, category=s.category),
            position=s.position,
            count=per_status.get(s.id, 0),
        )
        for s in statuses
    ]
    total = sum(c.count for c in by_status)
    completed = sum(c.count for c in by_status if c.status.category == StatusCategory.DONE.value)
    blocked = sum(c.count for c in by_status if c.status.category == StatusCategory.BLOCKED.value)
    next_milestone = (await manager_service.next_milestones(session, [project_id])).get(project_id)
    return TaskStatsOut(
        today=today,
        total=total,
        open=total - completed,
        completed=completed,
        progress_percent=completed * 100 // total if total else None,
        due_this_week=due_this_week,
        overdue=overdue,
        blocked=blocked,
        team_members=team_members or 0,
        team_functions=team_functions or 0,
        next_milestone=next_milestone,
        by_status=by_status,
        by_priority=[
            PriorityCount(priority=p, count=per_priority.get(p.value, 0)) for p in PRIORITY_ORDER
        ],
    )
