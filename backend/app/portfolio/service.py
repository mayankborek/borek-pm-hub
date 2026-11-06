"""Oversight across projects: the portfolio and who has access to what."""

import csv
import io
import uuid
from collections import defaultdict

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import (
    account_manager_condition,
    sees_all_projects,
    works_on_tasks_condition,
)
from app.common.enums import GlobalRole, ProjectRole, ProjectStatus, RagStatus
from app.common.validation import like_escape
from app.finance import service as finance_service
from app.organisations.models import OrganisationAccountManager
from app.organisations.schemas import PersonBrief
from app.portfolio.schemas import (
    AccessPerson,
    AccessProject,
    PortfolioOut,
    PortfolioProject,
    PortfolioSort,
)
from app.projects import service as project_service
from app.projects.membership import visible_project_ids
from app.projects.models import Project, ProjectMember
from app.projects.schemas import TaskSummary
from app.reporting.service import latest_published
from app.tasks.transfer import BOM, SEPARATOR, protect_cell
from app.users.models import User

CLIENT_ASSIGNMENT = "client_assignment"
ACCOUNT_MANAGER_ROLE = "account_manager"


def _order_by(sort: PortfolioSort) -> list[object]:
    descending = sort.startswith("-")
    column = getattr(Project, sort.lstrip("-"))
    primary = (column.desc() if descending else column.asc()).nulls_last()
    return [primary, Project.code]


async def _leads_and_counts(
    session: AsyncSession, project_ids: list[uuid.UUID]
) -> tuple[dict[uuid.UUID, list[PersonBrief]], dict[uuid.UUID, int]]:
    leads: dict[uuid.UUID, list[PersonBrief]] = defaultdict(list)
    counts: dict[uuid.UUID, int] = defaultdict(int)
    if not project_ids:
        return leads, counts
    rows = await session.execute(
        select(ProjectMember.project_id, ProjectMember.project_role, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id.in_(project_ids))
        .order_by(User.name, User.id)
    )
    for project_id, role, user in rows.all():
        counts[project_id] += 1
        if role == ProjectRole.PROJECT_LEAD.value:
            leads[project_id].append(PersonBrief(id=user.id, name=user.name, email=user.email))
    return leads, counts


async def portfolio(
    session: AsyncSession,
    user: User,
    *,
    q: str | None,
    status: ProjectStatus | None,
    client_organisation_id: uuid.UUID | None,
    rag: RagStatus | None,
    sort: PortfolioSort,
    page: int,
    page_size: int,
) -> PortfolioOut:
    """Active projects: all of them for a Manager, an Account Manager's clients' for them."""
    conditions: list[ColumnElement[bool]] = [Project.archived_at.is_(None)]
    if not sees_all_projects(user):
        conditions.append(Project.id.in_(visible_project_ids(user)))
    if status:
        conditions.append(Project.status == status.value)
    if client_organisation_id:
        conditions.append(Project.client_organisation_id == client_organisation_id)
    if q and q.strip():
        pattern = f"%{like_escape(q.strip())}%"
        conditions.append(
            or_(Project.name.ilike(pattern, escape="\\"), Project.code.ilike(pattern, escape="\\"))
        )

    latest = latest_published().subquery()
    if rag:
        conditions.append(
            Project.id.in_(select(latest.c.project_id).where(latest.c.rag == rag.value))
        )

    status_rows = await session.execute(
        select(Project.status, func.count(Project.id)).where(*conditions).group_by(Project.status)
    )
    by_status = {row[0]: row[1] for row in status_rows.all()}
    total = sum(by_status.values())

    live_ids = list(
        await session.scalars(
            select(Project.id).where(*conditions, Project.status != ProjectStatus.CANCELLED.value)
        )
    )
    live_summaries = await project_service.task_summaries(session, live_ids)
    totals = list(live_summaries.values())
    summary = project_service.make_summary(
        sum(s.total for s in totals),
        sum(s.completed for s in totals),
        sum(s.in_progress for s in totals),
        sum(s.blocked for s in totals),
        sum(s.overdue for s in totals),
    )

    rags = {
        row.project_id: row
        for row in (
            await session.execute(select(latest).where(latest.c.project_id.in_(live_ids)))
        ).all()
    }
    by_rag: dict[str, int] = defaultdict(int)
    for project_id in live_ids:
        by_rag[rags[project_id].rag if project_id in rags else "none"] += 1

    projects = list(
        await session.scalars(
            select(Project)
            .where(*conditions)
            .order_by(*_order_by(sort))  # type: ignore[arg-type]
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    ids = [p.id for p in projects]
    summaries = await project_service.task_summaries(session, ids)
    clients = await project_service.client_organisations(session, projects)
    leads, counts = await _leads_and_counts(session, ids)
    finance = await finance_service.summaries(session, ids)
    page_rags = {
        row.project_id: row
        for row in (await session.execute(select(latest).where(latest.c.project_id.in_(ids)))).all()
    }
    return PortfolioOut(
        items=[
            PortfolioProject(
                id=p.id,
                code=p.code,
                name=p.name,
                status=p.status,
                start_date=p.start_date,
                target_end_date=p.target_end_date,
                client_organisation=clients.get(p.client_organisation_id),
                leads=leads[p.id],
                member_count=counts[p.id],
                tasks=summaries.get(p.id, TaskSummary()),
                rag=page_rags[p.id].rag if p.id in page_rags else None,
                rag_date=page_rags[p.id].report_date if p.id in page_rags else None,
                finance=finance.get(p.id),
            )
            for p in projects
        ],
        total=total,
        page=page,
        page_size=page_size,
        by_status=by_status,
        by_rag=dict(by_rag),
        summary=summary,
    )


def _access_conditions(
    q: str | None, role: GlobalRole | None, project_id: uuid.UUID | None
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [
        or_(works_on_tasks_condition(), account_manager_condition())
    ]
    if role:
        conditions.append(User.global_role == role.value)
    if q and q.strip():
        pattern = f"%{like_escape(q.strip())}%"
        conditions.append(
            or_(User.name.ilike(pattern, escape="\\"), User.email.ilike(pattern, escape="\\"))
        )
    if project_id:
        client = select(Project.client_organisation_id).where(Project.id == project_id)
        conditions.append(
            or_(
                User.id.in_(
                    select(ProjectMember.user_id).where(ProjectMember.project_id == project_id)
                ),
                User.id.in_(
                    select(OrganisationAccountManager.user_id).where(
                        OrganisationAccountManager.organisation_id.in_(client)
                    )
                ),
            )
        )
    return conditions


async def _access_rows(
    session: AsyncSession, user_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[AccessProject]]:
    found: dict[uuid.UUID, list[AccessProject]] = defaultdict(list)
    if not user_ids:
        return found
    members = await session.execute(
        select(
            ProjectMember.user_id,
            Project.id,
            Project.code,
            Project.name,
            ProjectMember.project_role,
            ProjectMember.source,
        )
        .join(Project, Project.id == ProjectMember.project_id)
        .where(ProjectMember.user_id.in_(user_ids), Project.archived_at.is_(None))
    )
    clients = await session.execute(
        select(OrganisationAccountManager.user_id, Project.id, Project.code, Project.name)
        .join(
            Project,
            Project.client_organisation_id == OrganisationAccountManager.organisation_id,
        )
        .where(OrganisationAccountManager.user_id.in_(user_ids), Project.archived_at.is_(None))
    )
    for user_id, project_id, code, name, role, source in members.all():
        found[user_id].append(
            AccessProject(
                project_id=project_id,
                project_code=code,
                project_name=name,
                project_role=role,
                source=source,
            )
        )
    for user_id, project_id, code, name in clients.all():
        found[user_id].append(
            AccessProject(
                project_id=project_id,
                project_code=code,
                project_name=name,
                project_role=ACCOUNT_MANAGER_ROLE,
                source=CLIENT_ASSIGNMENT,
            )
        )
    for projects in found.values():
        projects.sort(key=lambda p: p.project_code)
    return found


async def access_overview(
    session: AsyncSession,
    *,
    q: str | None,
    role: GlobalRole | None,
    project_id: uuid.UUID | None,
    page: int,
    page_size: int | None,
) -> tuple[list[AccessPerson], int]:
    """People and the active projects they reach. Without `page_size`: everyone (the export)."""
    conditions = _access_conditions(q, role, project_id)
    total = await session.scalar(select(func.count(User.id)).where(*conditions)) or 0
    query = select(User).where(*conditions).order_by(User.name, User.id)
    if page_size is not None:
        query = query.offset((page - 1) * page_size).limit(page_size)
    users = list(await session.scalars(query))
    rows = await _access_rows(session, [u.id for u in users])
    return [
        AccessPerson(
            id=u.id,
            name=u.name,
            email=u.email,
            role=u.global_role,
            is_active=u.is_active,
            projects=rows[u.id],
        )
        for u in users
    ], total


def access_csv(people: list[AccessPerson]) -> bytes:
    """One row per person and project; people without a project get one row with empty cells.
    Same file format as the task export (UTF-8 with BOM, semicolons)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=SEPARATOR)
    writer.writerow(
        ["Name", "Email", "Role", "Active", "Project key", "Project", "Project role", "Source"]
    )
    for person in people:
        base = [
            protect_cell(person.name),
            protect_cell(person.email),
            person.role,
            "yes" if person.is_active else "no",
        ]
        if not person.projects:
            writer.writerow([*base, "", "", "", ""])
        for project in person.projects:
            writer.writerow(
                [
                    *base,
                    protect_cell(project.project_code),
                    protect_cell(project.project_name),
                    project.project_role,
                    project.source,
                ]
            )
    return (BOM + buffer.getvalue()).encode("utf-8")
