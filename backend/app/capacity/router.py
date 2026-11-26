"""Team capacity and workload (Manager > Team), working schedules and project reservations.

Workload and capacity: Managers. Schedules: read by Managers, changed by Admins and Managers.
Reservations: project leads and Managers of the project.
"""

import uuid
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action, can, require
from app.capacity import service
from app.capacity.schemas import (
    CapacityOut,
    ReservationCreate,
    ReservationOut,
    ReservationUpdate,
    ScheduleIn,
    ScheduleOut,
    WorkloadOut,
)
from app.core.database import SessionDep
from app.core.errors import AppError
from app.projects.service import authorize

router = APIRouter(tags=["team"])


def _read_schedules(user: CurrentUser) -> None:
    if not (can(user, Action.TEAM_VIEW) or can(user, Action.SCHEDULE_MANAGE)):
        raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")


@router.get("/manager/workload", response_model=WorkloadOut)
async def workload(user: CurrentUser, session: SessionDep) -> WorkloadOut:
    """Open and overdue tasks and remaining estimated effort (person-days) per person and
    project, highest effort first, plus unassigned work."""
    require(user, Action.TEAM_WORKLOAD)
    return await service.workload(session)


@router.get("/manager/capacity", response_model=CapacityOut)
async def capacity(
    user: CurrentUser,
    session: SessionDep,
    start: date | None = None,
    weeks: Annotated[int, Query(ge=1, le=78)] = 52,
) -> CapacityOut:
    """Reservations against working schedules: per person timeline segments, weekly totals,
    project and combined percentages, status, free-day labels and the summary cards.
    `start` defaults to Monday of this week."""
    require(user, Action.TEAM_VIEW)
    today = service.today()
    first = start or today - timedelta(days=today.weekday())
    return await service.capacity(session, first, weeks)


@router.get("/manager/schedule", response_model=ScheduleOut)
async def get_workspace_schedule(user: CurrentUser, session: SessionDep) -> ScheduleOut:
    """The workspace default working week (40 h Monday-Friday until changed)."""
    _read_schedules(user)
    return await service.workspace_schedule(session)


@router.put("/manager/schedule", response_model=ScheduleOut)
async def set_workspace_schedule(
    body: ScheduleIn, user: CurrentUser, session: SessionDep
) -> ScheduleOut:
    require(user, Action.SCHEDULE_MANAGE)
    return await service.set_workspace_schedule(session, user, body)


@router.get("/manager/people/{user_id}/schedule", response_model=ScheduleOut)
async def get_personal_schedule(
    user_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ScheduleOut:
    """The person's schedule: their own one (`source: personal`) or the workspace default."""
    _read_schedules(user)
    return await service.get_personal_schedule(session, user_id)


@router.put("/manager/people/{user_id}/schedule", response_model=ScheduleOut)
async def set_personal_schedule(
    user_id: uuid.UUID, body: ScheduleIn, user: CurrentUser, session: SessionDep
) -> ScheduleOut:
    """For part-time staff: their weekly hours and working days."""
    require(user, Action.SCHEDULE_MANAGE)
    return await service.set_personal_schedule(session, user, user_id, body)


@router.delete("/manager/people/{user_id}/schedule", response_model=ScheduleOut)
async def clear_personal_schedule(
    user_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ScheduleOut:
    """Back to the workspace default."""
    require(user, Action.SCHEDULE_MANAGE)
    return await service.clear_personal_schedule(session, user, user_id)


RES = "/projects/{project_id}/reservations"


@router.get(RES, response_model=list[ReservationOut])
async def list_reservations(
    project_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[ReservationOut]:
    """The project's reservations, by start date."""
    await authorize(session, user, project_id, Action.RESERVATION_MANAGE)
    return await service.reservations_out(
        session, await service.list_reservations(session, project_id)
    )


@router.post(RES, response_model=ReservationOut, status_code=201)
async def create_reservation(
    project_id: uuid.UUID, body: ReservationCreate, user: CurrentUser, session: SessionDep
) -> ReservationOut:
    """Planned hours per standard week for a project member between two dates (inclusive).
    Independent of tasks: estimates and assignments never create one."""
    await authorize(session, user, project_id, Action.RESERVATION_MANAGE, writable=True)
    row = await service.create_reservation(session, user, project_id, body)
    return (await service.reservations_out(session, [row]))[0]


@router.patch(RES + "/{reservation_id}", response_model=ReservationOut)
async def update_reservation(
    project_id: uuid.UUID,
    reservation_id: uuid.UUID,
    body: ReservationUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> ReservationOut:
    await authorize(session, user, project_id, Action.RESERVATION_MANAGE, writable=True)
    row = await service.update_reservation(session, user, project_id, reservation_id, body)
    return (await service.reservations_out(session, [row]))[0]


@router.delete(RES + "/{reservation_id}", status_code=204)
async def archive_reservation(
    project_id: uuid.UUID, reservation_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Response:
    """Archived, not deleted; it no longer counts in capacity."""
    await authorize(session, user, project_id, Action.RESERVATION_MANAGE, writable=True)
    await service.archive_reservation(session, user, project_id, reservation_id)
    return Response(status_code=204)
