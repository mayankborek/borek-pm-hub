from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import ColumnElement, func, or_, select

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action, require
from app.common.enums import GlobalRole
from app.core.database import SessionDep
from app.users.models import User
from app.users.schemas import UserListItem, UserListOut

router = APIRouter(prefix="/users", tags=["users"])


def _like_escape(text: str) -> str:
    """Make %, _ and the escape character itself literal in a LIKE pattern."""
    return text.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


@router.get("", response_model=UserListOut)
async def list_users(
    user: CurrentUser,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100, description="Search name or email")] = None,
    role: Annotated[GlobalRole | None, Query(description="pm or developer")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> UserListOut:
    """Active users, for the assignee picker (PM only). A task can be assigned to anyone listed."""
    require(user, Action.USER_LIST)
    conditions: list[ColumnElement[bool]] = [User.is_active.is_(True)]
    if role:
        conditions.append(User.global_role == role.value)
    if q and q.strip():
        pattern = f"%{_like_escape(q.strip())}%"
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
