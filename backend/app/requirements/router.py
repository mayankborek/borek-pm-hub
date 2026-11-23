"""Requirements of a project (staff side). Clients use /client/projects/{id}/requirements.

Read: everyone who can see the project. Create, edit, publish for acceptance and archive:
project leads and Managers.
"""

import uuid

from fastapi import APIRouter, Response

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action
from app.core.database import SessionDep
from app.projects.service import authorize
from app.requirements import service
from app.requirements.models import RequirementStatus
from app.requirements.schemas import (
    RequirementCreate,
    RequirementListOut,
    RequirementOut,
    RequirementUpdate,
    RequirementVersionRef,
)

router = APIRouter(prefix="/projects/{project_id}/requirements", tags=["requirements"])


@router.get("", response_model=RequirementListOut)
async def list_requirements(
    project_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    status: RequirementStatus | None = None,
) -> RequirementListOut:
    """By code, with every version and the client's answers, and counts per status (acceptance
    tracking)."""
    await authorize(session, user, project_id, Action.PROJECT_VIEW)
    rows, counts = await service.list_requirements(session, project_id, status)
    return RequirementListOut(
        items=await service.requirements_out(session, rows), total=len(rows), counts=counts
    )


@router.post("", response_model=RequirementOut, status_code=201)
async def create_requirement(
    project_id: uuid.UUID,
    body: RequirementCreate,
    user: CurrentUser,
    session: SessionDep,
    response: Response,
) -> RequirementOut:
    """A draft with version 1 and the next code (REQ-01, REQ-02 ...)."""
    await authorize(session, user, project_id, Action.REQUIREMENT_MANAGE, writable=True)
    requirement = await service.create_requirement(session, user, project_id, body)
    response.headers["Location"] = f"/api/v1/projects/{project_id}/requirements/{requirement.id}"
    return (await service.requirements_out(session, [requirement]))[0]


@router.get("/{requirement_id}", response_model=RequirementOut)
async def get_requirement(
    project_id: uuid.UUID, requirement_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> RequirementOut:
    await authorize(session, user, project_id, Action.PROJECT_VIEW)
    requirement = await service.get_requirement(session, project_id, requirement_id)
    return (await service.requirements_out(session, [requirement]))[0]


@router.patch("/{requirement_id}", response_model=RequirementOut)
async def update_requirement(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    body: RequirementUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> RequirementOut:
    """Editing the content of a published version starts a new draft version (409
    REQUIREMENT_CLOSED once accepted or rejected)."""
    await authorize(session, user, project_id, Action.REQUIREMENT_MANAGE, writable=True)
    requirement = await service.update_requirement(session, user, project_id, requirement_id, body)
    return (await service.requirements_out(session, [requirement]))[0]


@router.post("/{requirement_id}/publish", response_model=RequirementOut)
async def publish_requirement(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    body: RequirementVersionRef,
    user: CurrentUser,
    session: SessionDep,
) -> RequirementOut:
    """Publish the newest (draft) version for client acceptance: status awaiting_acceptance.
    Needs at least one acceptance criterion and an external project with a client (409
    NO_CLIENT); 409 NOTHING_TO_PUBLISH when the newest version is already published. An older
    version the client did not answer becomes superseded."""
    project = await authorize(session, user, project_id, Action.REQUIREMENT_MANAGE, writable=True)
    requirement = await service.publish(session, user, project, requirement_id, body.version)
    return (await service.requirements_out(session, [requirement]))[0]


@router.delete("/{requirement_id}", status_code=204)
async def archive_requirement(
    project_id: uuid.UUID, requirement_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Response:
    """Archive: hidden from every list, the client portal included."""
    await authorize(session, user, project_id, Action.REQUIREMENT_MANAGE, writable=True)
    await service.archive(session, user, project_id, requirement_id)
    return Response(status_code=204)
