"""Project and project-member endpoints (F02)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.auth.invites import invite_url
from app.auth.permissions import Action, require
from app.change_requests.models import ChangeRequest, ChangeRequestStatus
from app.common.enums import ProjectStatus, ProjectType, TaskPriority
from app.common.validation import PageParam, PageSizeParam
from app.core.config import Settings, get_settings
from app.core.database import SessionDep
from app.manager import next_action
from app.organisations import members as organisation_members
from app.organisations.schemas import MemberInviteOut, OrganisationBrief, OrganisationMemberOut
from app.projects import invitations, people, service
from app.projects.invitations import ProjectInviteIn, ProjectInviteOut
from app.projects.membership import project_access
from app.projects.models import Project, ProjectMember
from app.projects.people import ProjectPeopleOut
from app.projects.schemas import (
    CategoryOut,
    ClientContactCreatedOut,
    MemberIn,
    MemberOut,
    MemberRoleUpdate,
    ProjectCreate,
    ProjectCreatedOut,
    ProjectDetailOut,
    ProjectListOut,
    ProjectOut,
    ProjectUpdate,
    TaskSummary,
)
from app.users.models import User

router = APIRouter(prefix="/projects", tags=["projects"])

SettingsDep = Annotated[Settings, Depends(get_settings)]


async def _invite_out(
    session: AsyncSession,
    response: Response,
    settings: Settings,
    person: User,
    kind: Literal["team", "client"],
    token: str,
    expires_at: datetime,
) -> ProjectInviteOut:
    response.headers["Cache-Control"] = "no-store"  # the link works once: keep it out of caches
    return ProjectInviteOut(
        person=(await organisation_members.to_out(session, [person]))[0],
        kind=kind,
        invite=MemberInviteOut(url=invite_url(token, settings), expires_at=expires_at),
    )


MAX_CATEGORY_SUGGESTIONS = 100


def _project_out(
    project: Project,
    summary: TaskSummary | None = None,
    client_organisation: OrganisationBrief | None = None,
) -> ProjectOut:
    return ProjectOut(
        id=project.id,
        code=project.code,
        name=project.name,
        description=project.description,
        status=project.status,
        start_date=project.start_date,
        target_end_date=project.target_end_date,
        type=project.project_type,
        category=project.category,
        priority=project.priority,
        created_by=project.created_by,
        created_at=project.created_at,
        updated_at=project.updated_at,
        archived_at=project.archived_at,
        archived_by=project.archived_by,
        client_organisation=client_organisation,
        version=project.version,
        task_summary=summary or TaskSummary(),
    )


def _member_out(member: ProjectMember, user: User) -> MemberOut:
    return MemberOut(
        user_id=user.id,
        name=user.name,
        email=user.email,
        project_role=member.project_role,
        granted_at=member.granted_at,
    )


async def _detail(session: AsyncSession, project: Project) -> ProjectDetailOut:
    summaries = await service.task_summaries(session, [project.id])
    members = await service.list_members(session, project.id)
    clients = await service.client_organisations(session, [project])
    base = _project_out(
        project, summaries.get(project.id), clients.get(project.client_organisation_id)
    )
    return ProjectDetailOut(**base.model_dump(), members=[_member_out(m, u) for m, u in members])


async def _require_view(session: AsyncSession, user: User, project_id: uuid.UUID) -> Project:
    """Load the project and apply the view rule: non-members get 404, never a hint it exists."""
    project = await service.get_project(session, project_id)
    access = await project_access(session, user, project)
    require(user, Action.PROJECT_VIEW, access.resource(project_id))
    return project


@router.post("", response_model=ProjectCreatedOut, status_code=201)
async def create_project(
    body: ProjectCreate,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    response: Response,
) -> ProjectCreatedOut:
    """`type: external` needs `client_organisation_id` (an existing client) or `new_client`
    (a new client organisation, optionally with a first contact who gets a client account and
    an invite link, returned once in `client_contact`). Everything is saved together or not."""
    require(user, Action.PROJECT_CREATE)
    project, contact = await service.create_project(session, user, body, settings)
    response.headers["Location"] = f"/api/v1/projects/{project.id}"
    created = ProjectCreatedOut(**(await _detail(session, project)).model_dump())
    if contact is not None:
        response.headers["Cache-Control"] = "no-store"  # the link works once
        created.client_contact = ClientContactCreatedOut(
            member=(await organisation_members.to_out(session, [contact.user]))[0],
            invite=MemberInviteOut(
                url=invite_url(contact.token, settings), expires_at=contact.expires_at
            ),
        )
    return created


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(
    user: CurrentUser,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100, description="Part of the name")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_CATEGORY_SUGGESTIONS)] = 20,
) -> list[CategoryOut]:
    """Categories already used on active projects, most used first: suggestions for the
    project form. A new category is made simply by saving it on a project."""
    require(user, Action.PROJECT_CREATE)
    return await service.list_categories(session, q, limit)


async def _change_requests_visible(
    session: AsyncSession, user: User, projects: list[Project]
) -> set[uuid.UUID]:
    """Projects on the page whose open change requests this reader may see (checked only where
    there is an open request)."""
    ids = [p.id for p in projects]
    if not ids:
        return set()
    with_open = set(
        await session.scalars(
            select(ChangeRequest.project_id).where(
                ChangeRequest.project_id.in_(ids),
                ChangeRequest.status.in_(
                    [ChangeRequestStatus.PENDING.value, ChangeRequestStatus.IN_REVIEW.value]
                ),
            )
        )
    )
    return {
        p.id
        for p in projects
        if p.id in with_open
        and await service.allowed_in(session, user, p, Action.CHANGE_REQUEST_VIEW)
    }


@router.get("", response_model=ProjectListOut)
async def list_projects(
    user: CurrentUser,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100, description="Search name or code")] = None,
    status: ProjectStatus | None = None,
    type: Annotated[ProjectType | None, Query(description="internal or external")] = None,
    priority: TaskPriority | None = None,
    category: Annotated[
        str | None, Query(max_length=100, description="Exact category, any letter case")
    ] = None,
    include_archived: Annotated[
        bool, Query(description="Manager: all. PM: those they led or archived. Developers: ignored")
    ] = False,
    page: PageParam = 1,
    page_size: PageSizeParam = 50,
) -> ProjectListOut:
    require(user, Action.PROJECT_LIST)
    projects, total = await service.list_projects(
        session,
        user,
        q=q,
        status=status.value if status else None,
        include_archived=include_archived,
        page=page,
        page_size=page_size,
        project_type=type.value if type else None,
        priority=priority.value if priority else None,
        category=category,
    )
    summaries = await service.task_summaries(session, [p.id for p in projects])
    clients = await service.client_organisations(session, projects)
    actions = await next_action.next_actions(
        session,
        [p.id for p in projects],
        change_requests_for=await _change_requests_visible(session, user, projects),
    )
    return ProjectListOut(
        items=[
            _project_out(p, summaries.get(p.id), clients.get(p.client_organisation_id)).model_copy(
                update={"next_action": actions.get(p.id)}
            )
            for p in projects
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{project_id}", response_model=ProjectDetailOut)
async def get_project(
    project_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ProjectDetailOut:
    project = await _require_view(session, user, project_id)
    return await _detail(session, project)


@router.patch("/{project_id}", response_model=ProjectDetailOut)
async def update_project(
    project_id: uuid.UUID, body: ProjectUpdate, user: CurrentUser, session: SessionDep
) -> ProjectDetailOut:
    await _require_manage(session, user, project_id, Action.PROJECT_UPDATE)
    project = await service.update_project(session, project_id, body, user)
    return await _detail(session, project)


@router.delete("/{project_id}", status_code=204)
async def archive_project(project_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    """Archive (soft delete). The project and its tasks stay in the database."""
    await _require_manage(session, user, project_id, Action.PROJECT_ARCHIVE)
    await service.archive_project(session, project_id, user)


async def _require_manage(
    session: AsyncSession, user: User, project_id: uuid.UUID, action: Action
) -> None:
    """Lead-only actions on an existing project: 404 if not a member, 403 if a plain member."""
    project = await service.get_project(session, project_id)
    access = await project_access(session, user, project)
    require(user, action, access.resource(project_id))


@router.get("/{project_id}/people", response_model=ProjectPeopleOut)
async def project_people(
    project_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ProjectPeopleOut:
    """People & Access: team, the client's Account Managers and client contacts, each with
    their sign-in status, plus what the reader may change (project leads, Managers, the
    client's Account Manager)."""
    project = await service.authorize(session, user, project_id, Action.PEOPLE_VIEW)
    return await people.project_people(session, user, project)


@router.post("/{project_id}/people/invite", response_model=ProjectInviteOut, status_code=201)
async def invite_person(
    project_id: uuid.UUID,
    body: ProjectInviteIn,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    response: Response,
) -> ProjectInviteOut:
    """Project leads and Managers: invite a new person. `team` = a new developer / PM joins
    this project; `client` = a new contact of the project's client (external projects). Returns
    the invite link once (no email yet); it works for 30 days. 409 EMAIL_TAKEN when the email
    already has an account (add existing people with POST /members)."""
    project = await service.authorize(
        session, user, project_id, Action.MEMBER_MANAGE, writable=True
    )
    person, token, expires_at = await invitations.invite(session, user, project, body, settings)
    return await _invite_out(session, response, settings, person, body.kind, token, expires_at)


@router.post("/{project_id}/people/{user_id}/invite", response_model=ProjectInviteOut)
async def resend_invite(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    response: Response,
) -> ProjectInviteOut:
    """Resend: a new link for a team member or client contact who has not joined yet (409
    ALREADY_JOINED otherwise). Older unused links stop working."""
    project = await service.authorize(
        session, user, project_id, Action.MEMBER_MANAGE, writable=True
    )
    person, kind, token, expires_at = await invitations.resend(
        session, user, project, user_id, settings
    )
    return await _invite_out(session, response, settings, person, kind, token, expires_at)


@router.delete("/{project_id}/people/{user_id}/invite", response_model=OrganisationMemberOut)
async def revoke_invite(
    project_id: uuid.UUID, user_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> OrganisationMemberOut:
    """Revoke: the open link stops working, the person stays listed (invite_expired)."""
    project = await service.authorize(
        session, user, project_id, Action.MEMBER_MANAGE, writable=True
    )
    person = await invitations.revoke(session, user, project, user_id)
    return (await organisation_members.to_out(session, [person]))[0]


@router.delete("/{project_id}/people/{user_id}", status_code=204)
async def remove_person(
    project_id: uuid.UUID, user_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    """Remove access. Team member: leaves the project (tasks here become unassigned). Client
    contact: the account is deactivated (client access is per organisation)."""
    project = await service.authorize(
        session, user, project_id, Action.MEMBER_MANAGE, writable=True
    )
    await invitations.remove(session, user, project, user_id)


@router.get("/{project_id}/members", response_model=list[MemberOut])
async def list_members(
    project_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[MemberOut]:
    await _require_view(session, user, project_id)
    return [_member_out(m, u) for m, u in await service.list_members(session, project_id)]


@router.post("/{project_id}/members", response_model=MemberOut, status_code=201)
async def add_member(
    project_id: uuid.UUID, body: MemberIn, user: CurrentUser, session: SessionDep
) -> MemberOut:
    await _require_manage(session, user, project_id, Action.MEMBER_MANAGE)
    project = await service.get_writable_project(session, project_id)
    member, member_user = await service.add_member(session, project, user, body)
    return _member_out(member, member_user)


@router.patch("/{project_id}/members/{user_id}", response_model=MemberOut)
async def change_member_role(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    body: MemberRoleUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> MemberOut:
    await _require_manage(session, user, project_id, Action.MEMBER_MANAGE)
    await service.get_writable_project(session, project_id)
    member, member_user = await service.change_member_role(
        session, project_id, user_id, body.project_role, user
    )
    return _member_out(member, member_user)


@router.delete("/{project_id}/members/{user_id}", status_code=204)
async def remove_member(
    project_id: uuid.UUID, user_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    """Remove a member. Their tasks in this project become unassigned (recorded in history)."""
    await _require_manage(session, user, project_id, Action.MEMBER_MANAGE)
    await service.get_writable_project(session, project_id)
    await service.remove_member(session, project_id, user_id, user)
