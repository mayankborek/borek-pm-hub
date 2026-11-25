"""The event catalog: which change notifies whom. Domain services call one function here next to
their audit or history record, inside the same transaction.

Tasks work like Jira: the assignee, the creator and @mentioned people hear about a task; project
leads also hear when one is blocked. Clients only hear about what they can see in the portal
(their requests, published reports and requirements, shared milestones). Nobody hears about their
own changes (`notify` drops the actor).

Types (the frontend builds the text from type + params):
- project.member_added  (params: code, name, project_role) to the person added
- task.assigned / task.unassigned / task.updated / task.blocked / task.commented /
  task.mentioned / task.attachment_added  (params: key, title, ...)
- change_request.submitted / .review_started / .decided / .commented  (params: code, title, ...)
- status_report.published  (params: title, report_date, health)
- project_report.shared  (params: title, kind) to the audiences newly added (app/project_reports)
- milestone.moved / .done / .shared / .late  (params: code, name, due_date, previous_due_date,
  days_late); moved/done/late go to leads + Managers, moved/done/shared to the client (shared
  milestones only)
- requirement.published / .answered  (params: code, title, version, decision)
"""

import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import is_client
from app.capacity.models import MilestoneLateAlert
from app.milestones.models import Milestone
from app.notifications.service import (
    Recipient,
    account_managers,
    client_contacts,
    managers,
    notify,
    project_leads,
)
from app.projects.models import Project
from app.users.models import User

if TYPE_CHECKING:  # avoids import cycles with the domain modules
    from app.change_requests.models import ChangeRequest
    from app.reporting.models import StatusReport
    from app.requirements.models import Requirement
    from app.tasks.models import Task


def _as(ids: Iterable[uuid.UUID | None], setting: str) -> list[Recipient]:
    return [(i, setting) for i in ids if i is not None]


async def _project(session: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await session.get(Project, project_id)
    assert project is not None
    return project


# --- projects -------------------------------------------------------------------------------------


async def members_added(
    session: AsyncSession,
    actor: User,
    project: Project,
    roles: dict[uuid.UUID, str],
) -> None:
    """Existing people put on a project (Developer Role Guide: an existing developer is invited
    to a project in the platform, no accept step). One notification per person with their role."""
    for user_id, role in roles.items():
        await notify(
            session,
            actor,
            "project.member_added",
            entity_type="project",
            entity_id=project.id,
            project_id=project.id,
            params={"code": project.code, "name": project.name, "project_role": role},
            recipients=_as([user_id], "projects"),
        )


# --- tasks ----------------------------------------------------------------------------------------


def _task_params(task: "Task", **extra: Any) -> dict[str, Any]:
    return {"key": task.key, "title": task.title, **extra}


async def _task(
    session: AsyncSession,
    actor: User,
    task: "Task",
    type_: str,
    recipients: list[Recipient],
    **params: Any,
) -> None:
    await notify(
        session,
        actor,
        type_,
        entity_type="task",
        entity_id=task.id,
        project_id=task.project_id,
        params=_task_params(task, **params),
        recipients=recipients,
    )


def _involved(task: "Task", *, skip: Iterable[uuid.UUID | None] = ()) -> list[Recipient]:
    """Assignee first (the stronger reason), then the reporter."""
    skipped = set(skip)
    return [
        r
        for r in _as([task.assignee_id], "tasks_assigned")
        + _as([task.reporter_id], "tasks_reported")
        if r[0] not in skipped
    ]


async def task_created(session: AsyncSession, actor: User, task: "Task") -> None:
    if task.assignee_id:
        await _task(
            session, actor, task, "task.assigned", _as([task.assignee_id], "tasks_assigned")
        )


async def task_changed(
    session: AsyncSession,
    actor: User,
    task: "Task",
    *,
    fields: list[str],
    old_assignee_id: uuid.UUID | None,
    status: str | None,
    became_blocked: bool,
) -> None:
    """One notification per save, naming every changed field ("changed status and due date").
    `task` already carries the new values."""
    if not fields:
        return
    newly_assigned = task.assignee_id if task.assignee_id != old_assignee_id else None
    if newly_assigned:
        await _task(session, actor, task, "task.assigned", _as([newly_assigned], "tasks_assigned"))
    if old_assignee_id and old_assignee_id != task.assignee_id:
        await _task(
            session, actor, task, "task.unassigned", _as([old_assignee_id], "tasks_assigned")
        )
    others = _involved(task, skip=[newly_assigned])
    extra: dict[str, Any] = {"fields": fields}
    if status is not None:
        extra["status"] = status
    await _task(session, actor, task, "task.updated", others, **extra)
    if became_blocked:
        leads = await project_leads(session, task.project_id)
        await _task(
            session,
            actor,
            task,
            "task.blocked",
            _as(leads, "blocked_tasks"),
            reason=task.blocked_reason,
        )


async def task_commented(
    session: AsyncSession,
    actor: User,
    task: "Task",
    comment_id: uuid.UUID,
    mentioned: list[uuid.UUID],
) -> None:
    """@mentioned people get "mentioned" (and not the plain comment notification as well)."""
    await _task(
        session,
        actor,
        task,
        "task.mentioned",
        _as(mentioned, "mentions"),
        comment_id=str(comment_id),
    )
    await _task(
        session,
        actor,
        task,
        "task.commented",
        _involved(task, skip=mentioned),
        comment_id=str(comment_id),
    )


async def task_mentioned(
    session: AsyncSession,
    actor: User,
    task: "Task",
    comment_id: uuid.UUID,
    added: list[uuid.UUID],
) -> None:
    """People newly @mentioned in an edited comment."""
    await _task(
        session, actor, task, "task.mentioned", _as(added, "mentions"), comment_id=str(comment_id)
    )


async def task_attachment_added(
    session: AsyncSession, actor: User, task: "Task", name: str
) -> None:
    await _task(session, actor, task, "task.attachment_added", _involved(task), name=name)


# --- change requests ----------------------------------------------------------------------------


async def _team(session: AsyncSession, project: Project) -> list[uuid.UUID]:
    return await project_leads(session, project.id) + await account_managers(session, project)


async def _change_request(
    session: AsyncSession,
    actor: User,
    request: "ChangeRequest",
    type_: str,
    recipients: list[Recipient],
    **params: Any,
) -> None:
    await notify(
        session,
        actor,
        type_,
        entity_type="change_request",
        entity_id=request.id,
        project_id=request.project_id,
        params={"code": request.code, "title": request.title, **params},
        recipients=recipients,
    )


async def change_request_submitted(
    session: AsyncSession, actor: User, request: "ChangeRequest"
) -> None:
    """Leads and the client's Account Managers; the client contacts too when staff raised it."""
    project = await _project(session, request.project_id)
    ids = await _team(session, project)
    if not is_client(actor):
        ids += await client_contacts(session, project)
    await _change_request(
        session,
        actor,
        request,
        "change_request.submitted",
        _as(ids, "change_requests"),
        by_client=is_client(actor),
    )


async def _followers(session: AsyncSession, request: "ChangeRequest") -> list[uuid.UUID]:
    """Who follows a request's progress: the client contacts, the person who raised it and the
    client's Account Managers."""
    project = await _project(session, request.project_id)
    return (
        await client_contacts(session, project)
        + [request.submitted_by]
        + await account_managers(session, project)
    )


async def change_request_review_started(
    session: AsyncSession, actor: User, request: "ChangeRequest"
) -> None:
    await _change_request(
        session,
        actor,
        request,
        "change_request.review_started",
        _as(await _followers(session, request), "change_requests"),
    )


async def change_request_decided(
    session: AsyncSession, actor: User, request: "ChangeRequest"
) -> None:
    await _change_request(
        session,
        actor,
        request,
        "change_request.decided",
        _as(await _followers(session, request), "change_requests"),
        decision=request.status,
    )


async def change_request_commented(
    session: AsyncSession, actor: User, request: "ChangeRequest", *, internal: bool
) -> None:
    """Internal notes stay with the team; shared messages reach the client contacts too."""
    project = await _project(session, request.project_id)
    contacts = await client_contacts(session, project)
    ids = await _team(session, project) + [request.submitted_by]
    if internal:
        ids = [i for i in ids if i not in contacts]  # a client who raised it never sees notes
    else:
        ids += contacts
    await _change_request(
        session,
        actor,
        request,
        "change_request.commented",
        _as(ids, "change_requests"),
        internal=internal,
    )


# --- status reports -----------------------------------------------------------------------------


async def report_published(session: AsyncSession, actor: User, report: "StatusReport") -> None:
    project = await _project(session, report.project_id)
    ids = await client_contacts(session, project) + await account_managers(session, project)
    await notify(
        session,
        actor,
        "status_report.published",
        entity_type="status_report",
        entity_id=report.id,
        project_id=report.project_id,
        params={"report_date": report.report_date.isoformat(), "rag": report.rag},
        recipients=_as(ids, "reports"),
    )


# --- milestones (clients: shared milestones only) ------------------------------------------------


def _milestone_params(milestone: Milestone, old_due: date | None = None) -> dict[str, Any]:
    return {
        "code": milestone.code,
        "name": milestone.name,
        "due_date": milestone.due_date.isoformat(),
        "previous_due_date": (
            old_due.isoformat() if old_due and old_due != milestone.due_date else None
        ),
    }


async def _oversight(session: AsyncSession, project_id: uuid.UUID) -> list[Recipient]:
    """Project leads and every Manager: who hears about any milestone of the project."""
    return _as(await project_leads(session, project_id) + await managers(session), "milestones")


async def milestone_changed(
    session: AsyncSession,
    actor: User,
    milestone: Milestone,
    *,
    was_visible: bool,
    old_due: date,
    was_done: bool,
) -> None:
    """Leads and Managers hear when any milestone moves or is reached; the client when a
    shared milestone moves, is reached, or is newly shared."""
    if milestone.archived_at is not None:
        return
    reached = milestone.completed_at is not None and not was_done
    moved = milestone.due_date != old_due
    change = "milestone.done" if reached else "milestone.moved" if moved else None
    params = _milestone_params(milestone, old_due)

    async def send(type_: str, recipients: list[Recipient]) -> None:
        await notify(
            session,
            actor,
            type_,
            entity_type="milestone",
            entity_id=milestone.id,
            project_id=milestone.project_id,
            params=params,
            recipients=recipients,
        )

    if change:
        await send(change, await _oversight(session, milestone.project_id))
    if not milestone.client_visible:
        return
    client_type = "milestone.shared" if not was_visible else change
    if client_type:
        project = await _project(session, milestone.project_id)
        await send(client_type, _as(await client_contacts(session, project), "milestones"))


async def milestones_running_late(session: AsyncSession) -> int:
    """Daily check: tell leads and Managers once per due date when an open milestone of an
    active project has passed it ("Running late"). Returns how many milestones were reported.
    The caller commits."""
    now = datetime.now(UTC).date()
    rows = list(
        await session.scalars(
            select(Milestone)
            .join(Project, Project.id == Milestone.project_id)
            .outerjoin(MilestoneLateAlert, MilestoneLateAlert.milestone_id == Milestone.id)
            .where(
                Milestone.archived_at.is_(None),
                Milestone.completed_at.is_(None),
                Milestone.due_date < now,
                Project.archived_at.is_(None),
                Project.status.not_in(["completed", "cancelled"]),
                or_(
                    MilestoneLateAlert.milestone_id.is_(None),
                    MilestoneLateAlert.due_date != Milestone.due_date,
                ),
            )
        )
    )
    for m in rows:
        await notify(
            session,
            None,
            "milestone.late",
            entity_type="milestone",
            entity_id=m.id,
            project_id=m.project_id,
            params={**_milestone_params(m), "days_late": (now - m.due_date).days},
            recipients=await _oversight(session, m.project_id),
        )
        alert = await session.get(MilestoneLateAlert, m.id)
        if alert is None:
            session.add(MilestoneLateAlert(milestone_id=m.id, due_date=m.due_date))
        else:
            alert.due_date = m.due_date
    return len(rows)


# --- requirements -------------------------------------------------------------------------------


async def requirement_published(
    session: AsyncSession, actor: User, requirement: "Requirement", version: int
) -> None:
    project = await _project(session, requirement.project_id)
    await notify(
        session,
        actor,
        "requirement.published",
        entity_type="requirement",
        entity_id=requirement.id,
        project_id=requirement.project_id,
        params={"code": requirement.code, "title": requirement.title, "version": version},
        recipients=_as(await client_contacts(session, project), "requirements"),
    )


async def requirement_answered(
    session: AsyncSession, actor: User, requirement: "Requirement", version: int, decision: str
) -> None:
    """The owner first, then the project leads and the client's Account Managers."""
    project = await _project(session, requirement.project_id)
    ids = [requirement.owner_id, *await _team(session, project)]
    await notify(
        session,
        actor,
        "requirement.answered",
        entity_type="requirement",
        entity_id=requirement.id,
        project_id=requirement.project_id,
        params={
            "code": requirement.code,
            "title": requirement.title,
            "version": version,
            "decision": decision,
        },
        recipients=_as(ids, "requirements"),
    )
