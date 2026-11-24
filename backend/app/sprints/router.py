"""Sprints (Jira-like) and the backlog.

Everyone who sees the project's tasks reads sprints (TASK_VIEW: members, the client's Account
Manager, Managers). Project leads and Managers plan, start, complete and remove them
(SPRINT_MANAGE). Tasks without a sprint are the backlog: `GET /projects/{id}/tasks?backlog=true`;
one sprint's tasks: `?sprint_id=`. Sprint history = `GET /projects/{id}/sprints?state=completed`
(10 per page by default).
"""

import uuid

from fastapi import APIRouter, Response

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action
from app.common.validation import PageParam, PageSizeParam
from app.core.database import SessionDep
from app.projects.service import authorize
from app.sprints import service
from app.sprints.models import SprintState
from app.sprints.schemas import (
    MoveTasks,
    MoveTasksOut,
    SprintComplete,
    SprintCreate,
    SprintDetailOut,
    SprintListOut,
    SprintOut,
    SprintStart,
    SprintUpdate,
)

router = APIRouter(prefix="/projects/{project_id}/sprints", tags=["sprints"])


@router.get("", response_model=SprintListOut)
async def list_sprints(
    project_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    state: SprintState | None = None,
    page: PageParam = 1,
    page_size: PageSizeParam = 10,
) -> SprintListOut:
    """Active first, then planned (by number), then completed (newest first). `state=completed`
    is the sprint history."""
    await authorize(session, user, project_id, Action.TASK_VIEW)
    sprints, total = await service.list_sprints(
        session, project_id, state=state, page=page, page_size=page_size
    )
    return SprintListOut(
        items=await service.sprints_out(session, sprints),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=SprintOut, status_code=201)
async def create_sprint(
    project_id: uuid.UUID,
    body: SprintCreate,
    user: CurrentUser,
    session: SessionDep,
    response: Response,
) -> SprintOut:
    """A new planned sprint with the next number."""
    await authorize(session, user, project_id, Action.SPRINT_MANAGE, writable=True)
    sprint = await service.create_sprint(session, user, project_id, body)
    response.headers["Location"] = f"/api/v1/projects/{project_id}/sprints/{sprint.id}"
    return (await service.sprints_out(session, [sprint]))[0]


@router.post("/move-tasks", response_model=MoveTasksOut)
async def move_tasks(
    project_id: uuid.UUID, body: MoveTasks, user: CurrentUser, session: SessionDep
) -> MoveTasksOut:
    """Puts up to 200 tasks into a planned or active sprint, or back into the backlog
    (`sprint_id: null`). Written to each task's history."""
    await authorize(session, user, project_id, Action.SPRINT_MANAGE, writable=True)
    return MoveTasksOut(moved=await service.move_tasks(session, user, project_id, body))


@router.get("/{sprint_id}", response_model=SprintDetailOut)
async def get_sprint(
    project_id: uuid.UUID, sprint_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> SprintDetailOut:
    """With its tasks: the current ones (planned, active), or the sprint report with each task's
    outcome (completed)."""
    await authorize(session, user, project_id, Action.TASK_VIEW)
    sprint = await service.get_sprint(session, project_id, sprint_id)
    return await service.sprint_detail(session, sprint)


@router.patch("/{sprint_id}", response_model=SprintOut)
async def update_sprint(
    project_id: uuid.UUID,
    sprint_id: uuid.UUID,
    body: SprintUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> SprintOut:
    """Name, goal and dates of a planned or active sprint (409 SPRINT_COMPLETED otherwise)."""
    await authorize(session, user, project_id, Action.SPRINT_MANAGE, writable=True)
    sprint = await service.update_sprint(session, user, project_id, sprint_id, body)
    return (await service.sprints_out(session, [sprint]))[0]


@router.post("/{sprint_id}/start", response_model=SprintOut)
async def start_sprint(
    project_id: uuid.UUID,
    sprint_id: uuid.UUID,
    body: SprintStart,
    user: CurrentUser,
    session: SessionDep,
) -> SprintOut:
    """409 SPRINT_ALREADY_ACTIVE while another sprint of the project is active."""
    await authorize(session, user, project_id, Action.SPRINT_MANAGE, writable=True)
    sprint = await service.start_sprint(session, user, project_id, sprint_id, body)
    return (await service.sprints_out(session, [sprint]))[0]


@router.post("/{sprint_id}/complete", response_model=SprintOut)
async def complete_sprint(
    project_id: uuid.UUID,
    sprint_id: uuid.UUID,
    body: SprintComplete,
    user: CurrentUser,
    session: SessionDep,
) -> SprintOut:
    """Records each task's outcome. Done tasks stay; unfinished ones move to
    `move_open_tasks_to`, a new sprint (`create_next_sprint`), or the backlog."""
    await authorize(session, user, project_id, Action.SPRINT_MANAGE, writable=True)
    sprint = await service.complete_sprint(session, user, project_id, sprint_id, body)
    return (await service.sprints_out(session, [sprint]))[0]


@router.delete("/{sprint_id}", status_code=204)
async def archive_sprint(
    project_id: uuid.UUID, sprint_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    """Removes a planned sprint (archived, the row stays); its tasks go back to the backlog.
    Active: 409 SPRINT_ACTIVE. Completed: 409 SPRINT_COMPLETED (history stays)."""
    await authorize(session, user, project_id, Action.SPRINT_MANAGE, writable=True)
    await service.archive_sprint(session, user, project_id, sprint_id)
