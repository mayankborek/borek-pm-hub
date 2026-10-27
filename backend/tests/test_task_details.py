"""Task details APIs: history, comments, attachments (files and links)."""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole
from app.core.config import get_settings
from app.projects.models import Project, ProjectMember
from app.tasks.models import Task
from app.users.models import User
from tests.conftest import make_project, make_task, make_user
from tests.test_auth import HEADER, build_app, client_for


@pytest.fixture(autouse=True)
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


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
    w.outsider = await make_user(session)
    w.project = await make_project(session, w.pm.id, code="DET")
    for user in (w.dev, w.other_dev):
        session.add(
            ProjectMember(project_id=w.project.id, user_id=user.id, project_role="developer")
        )
    await session.flush()
    w.task = await make_task(session, w.project, w.pm.id, title="Details")
    return w


def url(world: World, tail: str) -> str:
    return f"/api/v1/tasks/{world.task.id}/{tail}"


# --- history ----------------------------------------------------------------------------------


async def test_history_records_who_changed_what(client: httpx.AsyncClient, world: World) -> None:
    pm, dev = as_user(world.pm), as_user(world.dev)
    created = (
        await client.post(
            f"/api/v1/projects/{world.project.id}/tasks", headers=pm, json={"title": "Tracked"}
        )
    ).json()
    task_url = f"/api/v1/tasks/{created['id']}"
    statuses = (
        await client.get(f"/api/v1/projects/{world.project.id}/statuses", headers=pm)
    ).json()
    in_progress = next(s for s in statuses if s["name"] == "In progress")

    await client.put(
        f"{task_url}/assignee", headers=pm, json={"version": 1, "assignee_id": str(world.dev.id)}
    )
    await client.patch(
        task_url,
        headers=dev,
        json={"version": 2, "status_id": in_progress["id"], "progress": 30},
    )
    await client.patch(
        task_url, headers=pm, json={"version": 3, "title": "Renamed", "priority": "high"}
    )
    await client.patch(task_url, headers=pm, json={"version": 4, "title": "Renamed"})  # no change
    await client.delete(task_url, headers=pm)

    response = await client.get(f"{task_url}/activity", headers=pm)

    assert response.status_code == 200
    body = response.json()
    assert [a["action"] for a in body["items"]] == [
        "archived",
        "updated",
        "updated",
        "updated",
        "created",
    ]
    assert body["total"] == 5
    archived, renamed, started, assigned, made = body["items"]
    assert made["actor"]["name"] == "Pia PM" and made["changes"] == {}
    assert assigned["changes"] == {"assignee": [None, "Dana Dev"]}
    assert started["actor"]["name"] == "Dana Dev"
    assert started["changes"] == {"status": ["To do", "In progress"], "progress": [0, 30]}
    assert renamed["changes"] == {"title": ["Tracked", "Renamed"], "priority": ["medium", "high"]}
    assert archived["actor"]["name"] == "Pia PM"


async def test_history_is_visible_to_members_only(client: httpx.AsyncClient, world: World) -> None:
    assert (await client.get(url(world, "activity"), headers=as_user(world.dev))).status_code == 200
    assert (
        await client.get(url(world, "activity"), headers=as_user(world.outsider))
    ).status_code == 404
    assert (await client.get(url(world, "activity"))).status_code == 401


async def test_history_paginates(client: httpx.AsyncClient, world: World) -> None:
    for i in range(3):
        await client.post(
            url(world, "comments"), headers=as_user(world.dev), json={"body": f"c{i}"}
        )
    page = (
        await client.get(
            url(world, "activity"), headers=as_user(world.dev), params={"page_size": 2, "page": 2}
        )
    ).json()
    assert page["total"] == 3 and len(page["items"]) == 1


# --- comments ---------------------------------------------------------------------------------


async def test_comments_are_added_listed_edited_and_archived(
    client: httpx.AsyncClient, world: World
) -> None:
    dev, other, pm = as_user(world.dev), as_user(world.other_dev), as_user(world.pm)

    made = await client.post(url(world, "comments"), headers=dev, json={"body": "  First  "})
    assert made.status_code == 201
    comment = made.json()
    assert comment["body"] == "First" and comment["author"]["name"] == "Dana Dev"
    assert comment["edited_at"] is None
    await client.post(url(world, "comments"), headers=other, json={"body": "Second"})

    listed = await client.get(url(world, "comments"), headers=pm)
    assert [c["body"] for c in listed.json()] == ["First", "Second"]

    edited = await client.patch(
        url(world, f"comments/{comment['id']}"), headers=dev, json={"body": "First, edited"}
    )
    assert edited.json()["body"] == "First, edited" and edited.json()["edited_at"] is not None

    # nobody edits someone else's words, not even the PM
    for who in (other, pm):
        denied = await client.patch(
            url(world, f"comments/{comment['id']}"), headers=who, json={"body": "hijack"}
        )
        assert denied.status_code == 403
    # only the author or a PM can remove a comment
    assert (
        await client.delete(url(world, f"comments/{comment['id']}"), headers=other)
    ).status_code == 403
    assert (
        await client.delete(url(world, f"comments/{comment['id']}"), headers=pm)
    ).status_code == 204
    assert [c["body"] for c in (await client.get(url(world, "comments"), headers=dev)).json()] == [
        "Second"
    ]
    assert (
        await client.patch(url(world, f"comments/{comment['id']}"), headers=dev, json={"body": "x"})
    ).status_code == 404


async def test_comment_validation_and_access(client: httpx.AsyncClient, world: World) -> None:
    dev = as_user(world.dev)
    for bad in ({"body": "   "}, {"body": ""}, {"body": "x" * 5001}, {}, {"body": "ok", "x": 1}):
        assert (await client.post(url(world, "comments"), headers=dev, json=bad)).status_code == 422
    outsider = as_user(world.outsider)
    assert (
        await client.post(url(world, "comments"), headers=outsider, json={"body": "hi"})
    ).status_code == 404
    assert (await client.get(url(world, "comments"), headers=outsider)).status_code == 404
    assert (await client.post(url(world, "comments"), json={"body": "hi"})).status_code == 401


async def test_archived_task_takes_no_new_comments(
    client: httpx.AsyncClient, session: AsyncSession, world: World
) -> None:
    world.task.archived_at = datetime.now(UTC)
    await session.flush()
    response = await client.post(
        url(world, "comments"), headers=as_user(world.pm), json={"body": "late"}
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "TASK_ARCHIVED"


# --- link attachments -------------------------------------------------------------------------


async def test_links_are_added_listed_and_removed(client: httpx.AsyncClient, world: World) -> None:
    dev, other, pm = as_user(world.dev), as_user(world.other_dev), as_user(world.pm)

    named = await client.post(
        url(world, "attachments/link"),
        headers=dev,
        json={"url": "https://borek.sharepoint.com/doc/spec.docx", "name": "Spec"},
    )
    plain = await client.post(
        url(world, "attachments/link"), headers=dev, json={"url": "https://example.com/a/b"}
    )

    assert named.status_code == 201 and plain.status_code == 201
    assert named.json()["kind"] == "link" and named.json()["name"] == "Spec"
    assert named.json()["download_url"] is None
    assert plain.json()["name"] == "example.com"
    listed = (await client.get(url(world, "attachments"), headers=pm)).json()
    assert [a["name"] for a in listed] == ["Spec", "example.com"]

    link_id = named.json()["id"]
    assert (
        await client.delete(url(world, f"attachments/{link_id}"), headers=other)
    ).status_code == 403
    assert (
        await client.delete(url(world, f"attachments/{link_id}"), headers=dev)
    ).status_code == 204
    assert [
        a["name"] for a in (await client.get(url(world, "attachments"), headers=pm)).json()
    ] == ["example.com"]
    assert (
        await client.delete(url(world, f"attachments/{link_id}"), headers=dev)
    ).status_code == 404


async def test_only_web_links_are_accepted(client: httpx.AsyncClient, world: World) -> None:
    for bad in (
        "javascript:alert(1)",
        "ftp://host/file",
        "example.com",
        "https://",
        "data:text/html,x",
    ):
        response = await client.post(
            url(world, "attachments/link"), headers=as_user(world.dev), json={"url": bad}
        )
        assert response.status_code == 422, bad


# --- file attachments -------------------------------------------------------------------------


async def test_file_upload_list_and_download(
    client: httpx.AsyncClient, world: World, upload_dir: Path
) -> None:
    dev, other, outsider = as_user(world.dev), as_user(world.other_dev), as_user(world.outsider)

    uploaded = await client.post(
        url(world, "attachments"),
        headers=dev,
        files={"file": ("report.pdf", b"%PDF-1.4 hello", "application/pdf")},
    )

    assert uploaded.status_code == 201
    item = uploaded.json()
    assert item["kind"] == "file" and item["name"] == "report.pdf"
    assert item["size_bytes"] == 14 and item["content_type"] == "application/pdf"
    assert item["url"] is None and item["uploaded_by"]["name"] == "Dana Dev"
    assert item["download_url"] == url(world, f"attachments/{item['id']}/download")
    assert len(list(upload_dir.iterdir())) == 1  # stored under a random key

    # everyone who can see the task can download it
    downloaded = await client.get(item["download_url"], headers=other)
    assert downloaded.status_code == 200 and downloaded.content == b"%PDF-1.4 hello"
    assert "attachment" in downloaded.headers["content-disposition"]
    assert "report.pdf" in downloaded.headers["content-disposition"]
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    assert (await client.get(item["download_url"], headers=outsider)).status_code == 404
    assert (await client.get(item["download_url"])).status_code == 401

    # archiving hides it but keeps the stored file
    assert (
        await client.delete(url(world, f"attachments/{item['id']}"), headers=dev)
    ).status_code == 204
    assert (await client.get(item["download_url"], headers=dev)).status_code == 404
    assert len(list(upload_dir.iterdir())) == 1


async def test_upload_limits_and_file_names(
    client: httpx.AsyncClient, world: World, upload_dir: Path
) -> None:
    dev = as_user(world.dev)

    too_big = await client.post(
        url(world, "attachments"),
        headers=dev,
        files={"file": ("big.pdf", b"x" * (1024 * 1024 + 1))},
    )
    empty = await client.post(
        url(world, "attachments"), headers=dev, files={"file": ("e.txt", b"")}
    )
    missing = await client.post(url(world, "attachments"), headers=dev)
    sneaky = await client.post(
        url(world, "attachments"), headers=dev, files={"file": ("../../etc/passwd.txt", b"data")}
    )
    exact = await client.post(
        url(world, "attachments"), headers=dev, files={"file": ("max.pdf", b"x" * 1024 * 1024)}
    )

    refused = [
        await client.post(url(world, "attachments"), headers=dev, files={"file": (name, b"x")})
        for name in ("run.exe", "tool.py", "x.sh", "page.html", "archive.zip", "noext")
    ]
    allowed = [
        await client.post(url(world, "attachments"), headers=dev, files={"file": (name, b"x")})
        for name in ("a.DOCX", "b.xlsx", "c.png", "voice.m4a", "n.txt")
    ]
    assert {r.status_code for r in refused} == {415}
    assert refused[0].json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
    assert {r.status_code for r in allowed} == {201}

    assert too_big.status_code == 413 and too_big.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert empty.status_code == 422 and missing.status_code == 422
    assert sneaky.json()["name"] == "passwd.txt"  # only the base name is kept
    assert exact.status_code == 201
    assert len(list(upload_dir.iterdir())) == 2 + len(
        allowed
    )  # the rejected uploads left nothing behind
    assert all(p.parent == upload_dir for p in upload_dir.iterdir())


async def test_attachments_need_membership_and_history_notes_them(
    client: httpx.AsyncClient, world: World
) -> None:
    files = {"file": ("a.txt", b"hello", "text/plain")}
    assert (
        await client.post(url(world, "attachments"), headers=as_user(world.outsider), files=files)
    ).status_code == 404
    assert (
        await client.get(url(world, "attachments"), headers=as_user(world.outsider))
    ).status_code == 404

    added = await client.post(url(world, "attachments"), headers=as_user(world.dev), files=files)
    await client.delete(url(world, f"attachments/{added.json()['id']}"), headers=as_user(world.pm))
    history = (await client.get(url(world, "activity"), headers=as_user(world.pm))).json()["items"]
    assert [(a["action"], a["changes"]) for a in history] == [
        ("attachment_removed", {"attachment": ["a.txt", None]}),
        ("attachment_added", {"attachment": [None, "a.txt"]}),
    ]
