from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.auth.dependencies import CurrentUser
from app.auth.schemas import MembershipOut, MeOut, UserOut
from app.core.config import Settings, get_settings
from app.core.database import SessionDep
from app.core.errors import AppError
from app.projects.membership import list_memberships
from app.users.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_user_out(user: User) -> UserOut:
    return UserOut(id=user.id, name=user.name, email=user.email, role=user.global_role)


@router.get("/dev-users", response_model=list[UserOut])
async def dev_users(
    session: SessionDep, settings: Annotated[Settings, Depends(get_settings)]
) -> list[UserOut]:
    """Phase 1 user picker. Not available once real sign-in (AUTH_MODE=entra) is on."""
    if settings.auth_mode != "dev":
        raise AppError(404, "NOT_FOUND", "Not found.")
    result = await session.scalars(
        select(User).where(User.is_active.is_(True)).order_by(User.global_role, User.name)
    )
    return [_to_user_out(user) for user in result]


@router.get("/me", response_model=MeOut)
async def me(user: CurrentUser, session: SessionDep) -> MeOut:
    memberships = await list_memberships(session, user.id)
    return MeOut(
        **_to_user_out(user).model_dump(),
        is_active=user.is_active,
        memberships=[
            MembershipOut(
                project_id=m.project_id,
                project_code=m.project_code,
                project_name=m.project_name,
                project_role=m.project_role,
            )
            for m in memberships
        ],
    )
