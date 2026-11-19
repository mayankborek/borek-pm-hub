"""Organisations: administrators change them; others read them to pick a project's client."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.auth.invites import invite_url
from app.auth.permissions import Action, require
from app.common.enums import OrganisationType
from app.common.validation import PageParam, PageSizeParam
from app.core.config import Settings, get_settings
from app.core.database import SessionDep
from app.organisations import members, service
from app.organisations.schemas import (
    AccountManagersUpdate,
    MemberInviteOut,
    OrganisationCreate,
    OrganisationListOut,
    OrganisationMemberCreate,
    OrganisationMemberCreatedOut,
    OrganisationMemberListOut,
    OrganisationMemberOut,
    OrganisationOut,
    OrganisationUpdate,
    PersonBrief,
)
from app.users.models import User

router = APIRouter(prefix="/organisations", tags=["organisations"])

SettingsDep = Annotated[Settings, Depends(get_settings)]


async def _with_invite(
    session: AsyncSession,
    response: Response,
    settings: Settings,
    user: User,
    token: str,
    expires_at: datetime,
) -> OrganisationMemberCreatedOut:
    response.headers["Cache-Control"] = "no-store"  # the link works once: keep it out of caches
    return OrganisationMemberCreatedOut(
        member=(await members.to_out(session, [user]))[0],
        invite=MemberInviteOut(url=invite_url(token, settings), expires_at=expires_at),
    )


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


# --- members (client contacts), administrator only ----------------------------------------------


@router.get("/{organisation_id}/members", response_model=OrganisationMemberListOut)
async def list_members(
    organisation_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    page: PageParam = 1,
    page_size: PageSizeParam = 50,
) -> OrganisationMemberListOut:
    """Contacts of a client organisation with their invite status, active people first."""
    require(user, Action.ORGANISATION_MANAGE)
    people, total = await members.list_members(
        session, organisation_id, page=page, page_size=page_size
    )
    return OrganisationMemberListOut(
        items=await members.to_out(session, people), total=total, page=page, page_size=page_size
    )


@router.post(
    "/{organisation_id}/members", response_model=OrganisationMemberCreatedOut, status_code=201
)
async def add_member(
    organisation_id: uuid.UUID,
    body: OrganisationMemberCreate,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    response: Response,
) -> OrganisationMemberCreatedOut:
    """Creates a `client` account in this organisation and its invite link at once (shown only
    once; no email is sent yet). Clients see nothing in the hub until the client views exist."""
    require(user, Action.ORGANISATION_MANAGE)
    member, token, expires_at = await members.add_member(
        session, user, organisation_id, body, settings
    )
    return await _with_invite(session, response, settings, member, token, expires_at)


@router.post(
    "/{organisation_id}/members/{user_id}/invite", response_model=OrganisationMemberCreatedOut
)
async def renew_member_invite(
    organisation_id: uuid.UUID,
    user_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    response: Response,
) -> OrganisationMemberCreatedOut:
    """A new invite link (for example after the first expired); older unused links stop working."""
    require(user, Action.ORGANISATION_MANAGE)
    member, token, expires_at = await members.renew_invite(
        session, user, organisation_id, user_id, settings
    )
    return await _with_invite(session, response, settings, member, token, expires_at)


@router.delete("/{organisation_id}/members/{user_id}", response_model=OrganisationMemberOut)
async def remove_member(
    organisation_id: uuid.UUID, user_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> OrganisationMemberOut:
    """Deactivates the contact's account (nothing is deleted). Activate it again in Users."""
    require(user, Action.ORGANISATION_MANAGE)
    member = await members.remove_member(session, user, organisation_id, user_id)
    return (await members.to_out(session, [member]))[0]
