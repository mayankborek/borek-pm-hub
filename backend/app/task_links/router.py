"""Task links (Jira-like): blocks / is blocked by, relates to, duplicates, clones.

Everyone who sees the task reads its links (TASK_VIEW). People who work on the project's tasks
add and remove them (TASK_LINK: developers and PMs in the project, leads, Managers; not Account
Managers or clients). Both tasks must be in the same project.
"""

import uuid

from fastapi import APIRouter

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action
from app.core.database import SessionDep
from app.projects.membership import lead_rights_in
from app.task_links import service
from app.task_links.schemas import LinkIn, TaskLinkOut
from app.tasks.router import _task_for

router = APIRouter(prefix="/tasks/{task_id}/links", tags=["task links"])


@router.get("", response_model=list[TaskLinkOut])
async def list_links(
    task_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[TaskLinkOut]:
    """Read from this task's side, by type."""
    task = await _task_for(session, user, task_id, Action.TASK_VIEW)
    leads = await lead_rights_in(session, user, task.project_id)
    return await service.list_links(session, task, include_archived=leads)


@router.post("", response_model=TaskLinkOut, status_code=201)
async def add_link(
    task_id: uuid.UUID, body: LinkIn, user: CurrentUser, session: SessionDep
) -> TaskLinkOut:
    """409 LINK_EXISTS when the two tasks are already linked this way (either direction)."""
    task = await _task_for(session, user, task_id, Action.TASK_LINK, writable=True)
    return await service.add_link(session, task, user, body)


@router.delete("/{link_id}", status_code=204)
async def remove_link(
    task_id: uuid.UUID, link_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    task = await _task_for(session, user, task_id, Action.TASK_LINK, writable=True)
    await service.remove_link(session, task, user, link_id)
