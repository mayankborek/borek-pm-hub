"""@mentions in task comments (BB-04): only active project members, stored by id."""

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole
from app.projects.models import Project, ProjectMember
from app.tasks.models import Task, TaskCommentMention
from app.users.models import User
from tests.conftest import make_project, make_task, make_user
from tests.test_auth import HEADER, build_app, client_for


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


def as_user(user: User) -> dict[str, str]:
    return {HEADER: str(user.id)}


class World:
    pm: User
    dev: User
    other_dev: User
    outsider: User
    project: Project
    task: Task


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> World:
    w = World()
    w.pm = await make_user(session, GlobalRole.PM)
    w.pm.name = "Pia PM"
    w.dev = await make_user(session)
    w.dev.name = "Dana Dev"
    w.other_dev = await make_user(session)
    w.other_dev.name = "Ben Dev"
    w.outsider = await make_user(session)
    w.project = await make_project(session, w.pm.id, code="MEN")
    for user in (w.dev, w.other_dev):
        session.add(
            ProjectMember(project_id=w.project.id, user_id=user.id, project_role="developer")
        )
    await session.flush()
    w.task = await make_task(session, w.project, w.pm.id, title="Mentions")
    return w


def comments_url(world: World, tail: str = "") -> str:
    return f"/api/v1/tasks/{world.task.id}/comments{tail}"


def names(comment: dict[str, Any]) -> list[str]:
    return [m["name"] for m in comment["mentions"]]


async def test_mentions_are_saved_returned_sorted_and_listed(
    client: httpx.AsyncClient, world: World
) -> None:
    made = await client.post(
        comments_url(world),
        headers=as_user(world.pm),
        json={
            "body": "@Dana Dev @Ben Dev please check",
            "mention_ids": [str(world.dev.id), str(world.other_dev.id), str(world.dev.id)],
        },
    )

    assert made.status_code == 201
    assert names(made.json()) == ["Ben Dev", "Dana Dev"]  # by name, duplicates removed
    assert set(made.json()["mentions"][0]) == {"id", "name", "email"}
    listed = await client.get(comments_url(world), headers=as_user(world.dev))
    assert names(listed.json()[0]) == ["Ben Dev", "Dana Dev"]


async def test_a_comment_without_mentions_still_works(
    client: httpx.AsyncClient, world: World
) -> None:
    made = await client.post(comments_url(world), headers=as_user(world.dev), json={"body": "Hi"})

    assert made.status_code == 201
    assert made.json()["mentions"] == []


async def test_mentioning_a_non_member_or_inactive_person_is_rejected(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    gone = await make_user(session)
    gone.is_active = False
    session.add(
        ProjectMember(project_id=world.project.id, user_id=gone.id, project_role="developer")
    )
    await session.flush()

    for bad in (world.outsider.id, gone.id):
        response = await client.post(
            comments_url(world),
            headers=as_user(world.pm),
            json={"body": "x", "mention_ids": [str(world.dev.id), str(bad)]},
        )
        assert response.status_code == 422
        detail = response.json()["error"]["details"][0]
        assert detail["field"] == "mention_ids"
        assert detail["issue"] == "not_a_project_member"
        assert str(bad) in detail["message"]

    # Nothing was saved: no comment, no mention rows.
    listed = await client.get(comments_url(world), headers=as_user(world.pm))
    assert listed.json() == []
    assert await session.scalar(select(func.count()).select_from(TaskCommentMention)) == 0


async def test_too_many_mentions_are_rejected(client: httpx.AsyncClient, world: World) -> None:
    ids = [str(world.dev.id)] * 21

    response = await client.post(
        comments_url(world), headers=as_user(world.pm), json={"body": "x", "mention_ids": ids}
    )

    assert response.status_code == 422


async def test_edit_replaces_mentions_and_leaving_them_out_keeps_them(
    client: httpx.AsyncClient, world: World
) -> None:
    pm = as_user(world.pm)
    made = await client.post(
        comments_url(world), headers=pm, json={"body": "a", "mention_ids": [str(world.dev.id)]}
    )
    one = comments_url(world, f"/{made.json()['id']}")

    kept = await client.patch(one, headers=pm, json={"body": "b"})
    replaced = await client.patch(
        one, headers=pm, json={"body": "c", "mention_ids": [str(world.other_dev.id)]}
    )
    rejected = await client.patch(
        one, headers=pm, json={"body": "d", "mention_ids": [str(world.outsider.id)]}
    )
    cleared = await client.patch(one, headers=pm, json={"body": "e", "mention_ids": []})

    assert names(kept.json()) == ["Dana Dev"]
    assert names(replaced.json()) == ["Ben Dev"]
    assert rejected.status_code == 422
    assert cleared.json()["mentions"] == []
    listed = await client.get(comments_url(world), headers=pm)
    assert listed.json()[0]["body"] == "e"  # the rejected edit changed nothing
    assert listed.json()[0]["mentions"] == []


async def test_mentions_in_another_project_are_not_allowed(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    other = await make_project(session, world.pm.id, code="MEO")
    session.add(
        ProjectMember(project_id=other.id, user_id=world.outsider.id, project_role="developer")
    )
    await session.flush()

    response = await client.post(
        comments_url(world),
        headers=as_user(world.pm),
        json={"body": "x", "mention_ids": [str(world.outsider.id)]},
    )

    assert response.status_code == 422  # a member of some project, but not of this one
