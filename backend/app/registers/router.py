"""Project registers: `/projects/{id}/risks`, `/issues` and `/decisions` (same shape each).

Everyone who sees the project reads them (PROJECT_VIEW: members, the client's Account Manager,
Managers). Project leads and Managers write them (REGISTER_MANAGE). Clients have no access.
"""

import uuid

from fastapi import APIRouter, Response

from app.auth.dependencies import CurrentUser
from app.auth.permissions import Action
from app.core.database import SessionDep
from app.projects.service import authorize
from app.registers import service
from app.registers.models import RegisterKind
from app.registers.schemas import RegisterCreate, RegisterItemOut, RegisterListOut, RegisterUpdate

router = APIRouter(prefix="/projects/{project_id}", tags=["registers"])

PATHS = {
    RegisterKind.RISK: "risks",
    RegisterKind.ISSUE: "issues",
    RegisterKind.DECISION: "decisions",
}


def _add_routes(kind: RegisterKind) -> None:
    base = f"/{PATHS[kind]}"
    item = f"{base}/{{item_id}}"
    label = kind.value

    async def list_items(
        project_id: uuid.UUID, user: CurrentUser, session: SessionDep, status: str | None = None
    ) -> RegisterListOut:
        await authorize(session, user, project_id, Action.PROJECT_VIEW)
        items, counts = await service.list_items(session, project_id, kind, status)
        return RegisterListOut(
            items=await service.items_out(session, items),
            total=len(items),
            counts=dict(counts),
        )

    async def create_item(
        project_id: uuid.UUID,
        body: RegisterCreate,
        user: CurrentUser,
        session: SessionDep,
        response: Response,
    ) -> RegisterItemOut:
        await authorize(session, user, project_id, Action.REGISTER_MANAGE, writable=True)
        created = await service.create_item(session, user, project_id, kind, body)
        response.headers["Location"] = f"/api/v1/projects/{project_id}{base}/{created.id}"
        return (await service.items_out(session, [created]))[0]

    async def get_item(
        project_id: uuid.UUID, item_id: uuid.UUID, user: CurrentUser, session: SessionDep
    ) -> RegisterItemOut:
        await authorize(session, user, project_id, Action.PROJECT_VIEW)
        found = await service.get_item(session, project_id, kind, item_id)
        return (await service.items_out(session, [found]))[0]

    async def update_item(
        project_id: uuid.UUID,
        item_id: uuid.UUID,
        body: RegisterUpdate,
        user: CurrentUser,
        session: SessionDep,
    ) -> RegisterItemOut:
        await authorize(session, user, project_id, Action.REGISTER_MANAGE, writable=True)
        changed = await service.update_item(session, user, project_id, kind, item_id, body)
        return (await service.items_out(session, [changed]))[0]

    async def archive_item(
        project_id: uuid.UUID, item_id: uuid.UUID, user: CurrentUser, session: SessionDep
    ) -> None:
        await authorize(session, user, project_id, Action.REGISTER_MANAGE, writable=True)
        await service.archive_item(session, user, project_id, kind, item_id)

    order = "Risks: highest score first. Others: oldest first."
    router.add_api_route(
        base,
        list_items,
        methods=["GET"],
        response_model=RegisterListOut,
        summary=f"List {PATHS[kind]}",
        description=f"Active {PATHS[kind]}; `status` narrows. {order}",
        operation_id=f"list_{PATHS[kind]}",
    )
    router.add_api_route(
        base,
        create_item,
        methods=["POST"],
        status_code=201,
        response_model=RegisterItemOut,
        summary=f"Add a {label}",
        operation_id=f"create_{label}",
    )
    router.add_api_route(
        item,
        get_item,
        methods=["GET"],
        response_model=RegisterItemOut,
        summary=f"Get a {label}",
        operation_id=f"get_{label}",
    )
    router.add_api_route(
        item,
        update_item,
        methods=["PATCH"],
        response_model=RegisterItemOut,
        summary=f"Change a {label}",
        operation_id=f"update_{label}",
    )
    router.add_api_route(
        item,
        archive_item,
        methods=["DELETE"],
        status_code=204,
        summary=f"Archive a {label}",
        description="Archived, not deleted.",
        operation_id=f"archive_{label}",
    )


for _kind in RegisterKind:
    _add_routes(_kind)
