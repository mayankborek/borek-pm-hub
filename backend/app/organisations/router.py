"""Organisations: administrators change them; others read them to pick a project's client."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action, require
from app.common.enums import OrganisationType
from app.common.validation import PageParam, PageSizeParam
from app.core.database import SessionDep
from app.organisations import service
from app.organisations.schemas import (
    AccountManagersUpdate,
    OrganisationCreate,
    OrganisationListOut,
    OrganisationOut,
    OrganisationUpdate,
    PersonBrief,
)

router = APIRouter(prefix="/organisations", tags=["organisations"])


@router.get("", response_model=OrganisationListOut)
async def list_organisations(
    user: CurrentUser,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100, description="Search the name")] = None,
    type: Annotated[OrganisationType | None, Query(description="internal or client")] = None,
    include_archived: bool = False,
    page: PageParam = 1,
    page_size: PageSizeParam = 50,
) -> OrganisationListOut:
    require(user, Action.ORGANISATION_VIEW)
    organisations, total = await service.list_organisations(
        session,
        q=q,
        organisation_type=type,
        include_archived=include_archived,
        page=page,
        page_size=page_size,
    )
    return OrganisationListOut(
        items=await service.to_out(session, organisations),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=OrganisationOut, status_code=201)
async def create_organisation(
    body: OrganisationCreate, user: CurrentUser, session: SessionDep, response: Response
) -> OrganisationOut:
    require(user, Action.ORGANISATION_MANAGE)
    organisation = await service.create_organisation(session, user, body)
    response.headers["Location"] = f"/api/v1/organisations/{organisation.id}"
    return (await service.to_out(session, [organisation]))[0]


@router.get("/{organisation_id}", response_model=OrganisationOut)
async def get_organisation(
    organisation_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> OrganisationOut:
    require(user, Action.ORGANISATION_VIEW)
    organisation = await service.get_organisation(session, organisation_id)
    return (await service.to_out(session, [organisation]))[0]


@router.patch("/{organisation_id}", response_model=OrganisationOut)
async def update_organisation(
    organisation_id: uuid.UUID, body: OrganisationUpdate, user: CurrentUser, session: SessionDep
) -> OrganisationOut:
    require(user, Action.ORGANISATION_MANAGE)
    organisation = await service.update_organisation(session, user, organisation_id, body)
    return (await service.to_out(session, [organisation]))[0]


@router.delete("/{organisation_id}", status_code=204)
async def archive_organisation(
    organisation_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    """Archive, refused while active users or projects belong to it. Nothing is deleted."""
    require(user, Action.ORGANISATION_MANAGE)
    await service.archive_organisation(session, user, organisation_id)


@router.put("/{organisation_id}/account-managers", response_model=list[PersonBrief])
async def set_account_managers(
    organisation_id: uuid.UUID, body: AccountManagersUpdate, user: CurrentUser, session: SessionDep
) -> list[PersonBrief]:
    """Replace the account managers of a client. They see that client's projects, read-only."""
    require(user, Action.ORGANISATION_MANAGE)
    return await service.set_account_managers(session, user, organisation_id, body.user_ids)
