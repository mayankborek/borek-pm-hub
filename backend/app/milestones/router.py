"""Project roadmap: phases (bars) and milestones (diamonds).

Everyone who sees the project reads the roadmap (PROJECT_VIEW: members, Account Managers of the
client, Managers). Project leads and Managers change it (MILESTONE_MANAGE). Clients use
/client/projects/{id}/roadmap instead, which shows only what is marked visible to them.
"""

import uuid

from fastapi import APIRouter, Response

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action
from app.core.database import SessionDep
from app.milestones import service
from app.milestones.schemas import (
    MilestoneCreate,
    MilestoneDetailOut,
    MilestoneOut,
    MilestoneUpdate,
    PhaseCreate,
    PhaseOrder,
    PhaseOut,
    PhaseUpdate,
    RoadmapOut,
)
from app.projects.service import authorize

router = APIRouter(prefix="/projects/{project_id}", tags=["milestones"])


@router.get("/roadmap", response_model=RoadmapOut)
async def get_roadmap(project_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> RoadmapOut:
    """The roadmap screen in one call: date range, today, phases in order with their status,
    completed share and milestones, and milestones outside any phase."""
    project = await authorize(session, user, project_id, Action.PROJECT_VIEW)
    return await service.roadmap_out(session, project)


# --- phases -------------------------------------------------------------------------------------


@router.get("/phases", response_model=list[PhaseOut])
async def list_phases(
    project_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[PhaseOut]:
    """Active phases in roadmap order."""
    await authorize(session, user, project_id, Action.PROJECT_VIEW)
    roadmap = await service.build_roadmap(session, project_id)
    return [out for _, out, _ in roadmap.phases]


@router.post("/phases", response_model=PhaseOut, status_code=201)
async def create_phase(
    project_id: uuid.UUID,
    body: PhaseCreate,
    user: CurrentUser,
    session: SessionDep,
    response: Response,
) -> PhaseOut:
    """Added at the end of the roadmap."""
    await authorize(session, user, project_id, Action.MILESTONE_MANAGE, writable=True)
    phase = await service.create_phase(session, user, project_id, body)
    response.headers["Location"] = f"/api/v1/projects/{project_id}/phases/{phase.id}"
    return await service.phase_out_of(session, phase)


@router.put("/phases/order", status_code=204)
async def reorder_phases(
    project_id: uuid.UUID, body: PhaseOrder, user: CurrentUser, session: SessionDep
) -> None:
    """Send every active phase once, in the new order."""
    await authorize(session, user, project_id, Action.MILESTONE_MANAGE, writable=True)
    await service.reorder_phases(session, user, project_id, body.phase_ids)


@router.get("/phases/{phase_id}", response_model=PhaseOut)
async def get_phase(
    project_id: uuid.UUID, phase_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> PhaseOut:
    await authorize(session, user, project_id, Action.PROJECT_VIEW)
    phase = await service.get_phase(session, project_id, phase_id)
    return await service.phase_out_of(session, phase)


@router.patch("/phases/{phase_id}", response_model=PhaseOut)
async def update_phase(
    project_id: uuid.UUID,
    phase_id: uuid.UUID,
    body: PhaseUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> PhaseOut:
    await authorize(session, user, project_id, Action.MILESTONE_MANAGE, writable=True)
    phase = await service.update_phase(session, user, project_id, phase_id, body)
    return await service.phase_out_of(session, phase)


@router.delete("/phases/{phase_id}", status_code=204)
async def archive_phase(
    project_id: uuid.UUID, phase_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    """Archives an empty phase (409 PHASE_HAS_MILESTONES otherwise). The row stays."""
    await authorize(session, user, project_id, Action.MILESTONE_MANAGE, writable=True)
    await service.archive_phase(session, user, project_id, phase_id)


# --- milestones ---------------------------------------------------------------------------------


@router.get("/milestones", response_model=list[MilestoneOut])
async def list_milestones(
    project_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    phase_id: uuid.UUID | None = None,
) -> list[MilestoneOut]:
    """Active milestones by due date; `phase_id` narrows to one phase."""
    await authorize(session, user, project_id, Action.PROJECT_VIEW)
    milestones = await service.active_milestones(session, [project_id])
    if phase_id is not None:
        milestones = [m for m in milestones if m.phase_id == phase_id]
    return await service.milestones_out(session, milestones)


@router.post("/milestones", response_model=MilestoneOut, status_code=201)
async def create_milestone(
    project_id: uuid.UUID,
    body: MilestoneCreate,
    user: CurrentUser,
    session: SessionDep,
    response: Response,
) -> MilestoneOut:
    """Gets the next code (M-01, M-02 ...). Link tasks with `milestone_id` on the task."""
    await authorize(session, user, project_id, Action.MILESTONE_MANAGE, writable=True)
    milestone = await service.create_milestone(session, user, project_id, body)
    response.headers["Location"] = f"/api/v1/projects/{project_id}/milestones/{milestone.id}"
    return (await service.milestones_out(session, [milestone]))[0]


@router.get("/milestones/{milestone_id}", response_model=MilestoneDetailOut)
async def get_milestone(
    project_id: uuid.UUID, milestone_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> MilestoneDetailOut:
    """With its linked tasks."""
    await authorize(session, user, project_id, Action.PROJECT_VIEW)
    milestone = await service.get_milestone(session, project_id, milestone_id)
    return await service.milestone_detail(session, milestone)


@router.patch("/milestones/{milestone_id}", response_model=MilestoneOut)
async def update_milestone(
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    body: MilestoneUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> MilestoneOut:
    """Also marks it reached (`done: true`) or opens it again (`done: false`)."""
    await authorize(session, user, project_id, Action.MILESTONE_MANAGE, writable=True)
    milestone = await service.update_milestone(session, user, project_id, milestone_id, body)
    return (await service.milestones_out(session, [milestone]))[0]


@router.delete("/milestones/{milestone_id}", status_code=204)
async def archive_milestone(
    project_id: uuid.UUID, milestone_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    """Archives it; its tasks lose the link. The row stays."""
    await authorize(session, user, project_id, Action.MILESTONE_MANAGE, writable=True)
    await service.archive_milestone(session, user, project_id, milestone_id)
