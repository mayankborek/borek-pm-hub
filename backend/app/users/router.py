from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action, require, works_on_tasks_condition
from app.common.enums import GlobalRole
from app.common.validation import PageParam, PageSizeParam, like_escape
from app.core.database import SessionDep
from app.organisations.models import Organisation
from app.organisations.schemas import OrganisationBrief
from app.users.models import User
from app.users.schemas import ProfileOut, ProfileUpdate, UserListItem, UserListOut

router = APIRouter(prefix="/users", tags=["users"])
me_router = APIRouter(prefix="/me", tags=["users"])


@router.get("", response_model=UserListOut)
async def list_users(
    user: CurrentUser,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100, description="Search name or email")] = None,
    role: Annotated[GlobalRole | None, Query(description="pm, manager or developer")] = None,
    page: PageParam = 1,
    page_size: PageSizeParam = 50,
) -> UserListOut:
    """Active PMs, Managers and developers, for the assignee picker (PMs and Managers). The other
    roles do no project work, so they are not listed."""
    require(user, Action.USER_LIST)
    conditions: list[ColumnElement[bool]] = [User.is_active.is_(True), works_on_tasks_condition()]
    if role:
        conditions.append(User.global_role == role.value)
    if q and q.strip():
        pattern = f"%{like_escape(q.strip())}%"
        conditions.append(
            or_(User.name.ilike(pattern, escape="\\"), User.email.ilike(pattern, escape="\\"))
        )
    total = await session.scalar(select(func.count(User.id)).where(*conditions)) or 0
    rows = await session.scalars(
        select(User)
        .where(*conditions)
        .order_by(User.name, User.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return UserListOut(
        items=[UserListItem(id=u.id, name=u.name, email=u.email, role=u.global_role) for u in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


async def _profile(session: AsyncSession, user: User) -> ProfileOut:
    organisation = (
        await session.get(Organisation, user.organisation_id) if user.organisation_id else None
    )
    return ProfileOut(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.global_role,
        job_title=user.job_title,
        phone=user.phone,
        organisation=(
            OrganisationBrief(id=organisation.id, name=organisation.name) if organisation else None
        ),
    )


@me_router.get("/profile", response_model=ProfileOut)
async def get_profile(user: CurrentUser, session: SessionDep) -> ProfileOut:
    """The signed-in person's own profile (any role, clients included)."""
    return await _profile(session, user)


@me_router.patch("/profile", response_model=ProfileOut)
async def update_profile(body: ProfileUpdate, user: CurrentUser, session: SessionDep) -> ProfileOut:
    """Change your own phone number. Everything else is set by the administrator."""
    if "phone" in body.model_fields_set:
        user.phone = body.phone
        await session.commit()
    return await _profile(session, user)
