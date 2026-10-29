"""Hard input validation: bad input is refused with 422 in the one error shape, never a 500."""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GlobalRole
from app.core.config import get_settings
from app.projects.models import Project
from app.tasks.models import Task
from app.users.models import User
from tests.conftest import make_project, make_task, make_user
from tests.test_auth import HEADER, build_app, client_for

API = "/api/v1"


@pytest.fixture(autouse=True)
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(build_app(session)) as http:
        yield http


class World:
    pm: User
    headers: dict[str, str]
    project: Project
    task: Task


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> World:
    w = World()
    w.pm = await make_user(session, GlobalRole.PM)
    w.headers = {HEADER: str(w.pm.id)}
    w.project = await make_project(session, w.pm.id, code="HRD")
    w.task = await make_task(session, w.project, w.pm.id)
    return w


def assert_invalid(response: httpx.Response, field: str | None = None) -> None:
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert all("Value error" not in d["message"] for d in error["details"])
    if field is not None:
        assert field in [d["field"].split(".")[0] for d in error["details"]], error["details"]


# --- paging and filters -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "path", ["/users", "/projects", "/tasks", "/me/tasks", "/projects/{project}/tasks"]
)
async def test_huge_page_is_422_not_500(client: httpx.AsyncClient, world: World, path: str) -> None:
    url = API + path.format(project=world.project.id)
    assert_invalid(await client.get(url, headers=world.headers, params={"page": 10**18}), "page")
    assert_invalid(await client.get(url, headers=world.headers, params={"page": 0}), "page")
    assert_invalid(await client.get(url, headers=world.headers, params={"page_size": 201}))


async def test_unknown_priority_is_refused_everywhere(
    client: httpx.AsyncClient, world: World
) -> None:
    create = await client.post(
        f"{API}/projects/{world.project.id}/tasks",
        headers=world.headers,
        json={"title": "x", "priority": "critical"},
    )
    assert_invalid(create, "priority")
    update = await client.patch(
        f"{API}/tasks/{world.task.id}",
        headers=world.headers,
        json={"version": 1, "priority": "urgent"},
    )
    assert_invalid(update, "priority")
    assert_invalid(
        await client.get(f"{API}/tasks", headers=world.headers, params={"priority": "critical"}),
        "priority",
    )


async def test_filter_ranges_and_path_ids(client: httpx.AsyncClient, world: World) -> None:
    response = await client.get(
        f"{API}/tasks",
        headers=world.headers,
        params={"due_after": "2026-05-10", "due_before": "2026-05-01"},
    )
    assert_invalid(response, "due_after")
    assert_invalid(await client.get(f"{API}/tasks/not-a-uuid", headers=world.headers), "task_id")
    too_many = [("priority", "high")] * 11
    assert_invalid(await client.get(f"{API}/tasks", headers=world.headers, params=too_many))


async def test_search_with_backslash_matches_literally(
    client: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    await make_task(session, world.project, world.pm.id, title=r"path C:\temp")
    response = await client.get(f"{API}/tasks", headers=world.headers, params={"q": "\\"})
    assert response.status_code == 200
    assert [t["title"] for t in response.json()["items"]] == [r"path C:\temp"]


# --- text fields ------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["a\x00b", "bell\x07", "   "])
async def test_task_text_rejects_control_characters_and_blank(
    client: httpx.AsyncClient, world: World, session: AsyncSession, bad: str
) -> None:
    before = await session.scalar(select(func.count()).select_from(Task))
    url = f"{API}/projects/{world.project.id}/tasks"
    assert_invalid(await client.post(url, headers=world.headers, json={"title": bad}), "title")
    if bad.strip():
        for field in ("description", "blocked_reason"):
            body = {"title": "ok", field: bad}
            assert_invalid(await client.post(url, headers=world.headers, json=body), field)
    assert await session.scalar(select(func.count()).select_from(Task)) == before


async def test_long_and_blank_descriptions(client: httpx.AsyncClient, world: World) -> None:
    url = f"{API}/projects/{world.project.id}/tasks"
    too_long = {"title": "ok", "description": "x" * 20_001}
    assert_invalid(await client.post(url, headers=world.headers, json=too_long), "description")
    reason = {"title": "ok", "blocked_reason": "x" * 1_001}
    assert_invalid(await client.post(url, headers=world.headers, json=reason), "blocked_reason")
    blank = await client.post(url, headers=world.headers, json={"title": "ok", "description": "  "})
    assert blank.status_code == 201 and blank.json()["description"] is None
    ok = {"title": "ok", "description": "x" * 20_000}
    assert (await client.post(url, headers=world.headers, json=ok)).status_code == 201


async def test_task_patch_rejects_null_for_required_fields(
    client: httpx.AsyncClient, world: World
) -> None:
    for field in ("title", "priority", "labels", "status_id"):
        response = await client.patch(
            f"{API}/tasks/{world.task.id}", headers=world.headers, json={"version": 1, field: None}
        )
        assert_invalid(response, field)


async def test_task_dates_estimate_and_labels(client: httpx.AsyncClient, world: World) -> None:
    url = f"{API}/projects/{world.project.id}/tasks"

    async def post(**values: Any) -> httpx.Response:
        return await client.post(url, headers=world.headers, json={"title": "t", **values})

    assert_invalid(await post(start_date="1999-12-31"), "start_date")
    assert_invalid(await post(due_date="2101-01-01"), "due_date")
    assert_invalid(await post(start_date="2026-05-02", due_date="2026-05-01"))
    assert_invalid(await post(estimate_value=13, estimate_unit="weeks"), "estimate_value")
    assert_invalid(await post(estimate_value=161, estimate_unit="hours"), "estimate_value")
    assert_invalid(await post(estimate_value=4_801, estimate_unit="minutes"), "estimate_value")
    assert_invalid(await post(estimate_value=5), None)
    assert_invalid(await post(labels=[f"l{i}" for i in range(51)]), "labels")
    assert_invalid(await post(labels=["a\x00b"]), "labels")
    assert (await post(estimate_value=12, estimate_unit="weeks")).status_code == 201
    assert (await post(estimate_value=160, estimate_unit="hours")).status_code == 201
    assert (await post(estimate_value=4_800, estimate_unit="minutes")).status_code == 201


async def test_estimate_cap_cannot_be_bypassed_on_patch(
    client: httpx.AsyncClient, world: World
) -> None:
    url = f"{API}/tasks/{world.task.id}"
    hours = {"version": 1, "estimate_value": 90, "estimate_unit": "hours"}
    set_hours = await client.patch(url, headers=world.headers, json=hours)
    assert set_hours.status_code == 200

    # only the unit: 90 hours would become 90 weeks
    unit_only = await client.patch(
        url, headers=world.headers, json={"version": 2, "estimate_unit": "weeks"}
    )
    assert_invalid(unit_only, "estimate_value")
    # only the amount, above the hours cap
    value_only = await client.patch(
        url, headers=world.headers, json={"version": 2, "estimate_value": 161}
    )
    assert_invalid(value_only, "estimate_value")

    fits = await client.patch(
        url, headers=world.headers, json={"version": 2, "estimate_unit": "minutes"}
    )
    assert fits.status_code == 200 and fits.json()["estimate_value"] == 90


# --- projects ---------------------------------------------------------------------------------


@pytest.mark.parametrize("code", ["ſab", "ıabc", "ab cd", "a", "A" * 21, "ÄBC", "ab\x00"])
async def test_project_code_is_ascii_only(
    client: httpx.AsyncClient, world: World, code: str
) -> None:
    response = await client.post(
        f"{API}/projects", headers=world.headers, json={"code": code, "name": "P"}
    )
    assert_invalid(response, "code")


async def test_project_text_dates_and_members(
    client: httpx.AsyncClient, world: World, session: AsyncSession
) -> None:
    url = f"{API}/projects"
    count = select(func.count()).select_from(Project)
    before = await session.scalar(count)

    async def post(**values: Any) -> httpx.Response:
        return await client.post(
            url, headers=world.headers, json={"code": "NEW1", "name": "New", **values}
        )

    assert_invalid(await post(name="a\x00b"), "name")
    assert_invalid(await post(name="x" * 201), "name")
    assert_invalid(await post(description="x" * 20_001), "description")
    assert_invalid(await post(start_date="1900-01-01"), "start_date")
    assert_invalid(await post(target_end_date="2200-01-01"), "target_end_date")
    assert_invalid(await post(start_date="2026-02-01", target_end_date="2026-01-01"))
    member = {"user_id": str(world.pm.id)}
    assert_invalid(await post(members=[member] * 201), "members")
    assert_invalid(await post(code="a\u0000bc"), "code")
    assert await session.scalar(count) == before

    created = await post(code="  new1 ", description="   ")
    assert created.status_code == 201
    assert created.json()["code"] == "NEW1" and created.json()["description"] is None


async def test_project_patch_validation(client: httpx.AsyncClient, world: World) -> None:
    url = f"{API}/projects/{world.project.id}"
    for body in (
        {"version": 1, "name": "a\x00b"},
        {"version": 1, "description": "x" * 20_001},
        {"version": 1, "start_date": "1999-01-01"},
        {"version": 1, "status": "finished"},
    ):
        assert_invalid(await client.patch(url, headers=world.headers, json=body))


# --- status names, comments, links, uploads ---------------------------------------------------


async def test_status_name_rejects_control_characters(
    client: httpx.AsyncClient, world: World
) -> None:
    response = await client.post(
        f"{API}/projects/{world.project.id}/statuses",
        headers=world.headers,
        json={"name": "bad\x00name", "category": "todo"},
    )
    assert_invalid(response, "name")


async def test_comment_and_link_validation(client: httpx.AsyncClient, world: World) -> None:
    base = f"{API}/tasks/{world.task.id}"
    assert_invalid(
        await client.post(f"{base}/comments", headers=world.headers, json={"body": "a\x00b"}),
        "body",
    )
    multiline = await client.post(
        f"{base}/comments", headers=world.headers, json={"body": "line 1\nline 2"}
    )
    assert multiline.status_code == 201
    for url in (
        "https://user:secret@example.com/x",
        "https://exa mple.com",
        "https://example.com/\x00",
        "ftp://example.com",
        "https://",
    ):
        response = await client.post(
            f"{base}/attachments/link", headers=world.headers, json={"url": url}
        )
        assert_invalid(response, "url")
    named = await client.post(
        f"{base}/attachments/link",
        headers=world.headers,
        json={"url": "https://example.com:8080/a", "name": "  "},
    )
    assert named.status_code == 201 and named.json()["name"] == "example.com"
    assert_invalid(
        await client.post(
            f"{base}/attachments/link",
            headers=world.headers,
            json={"url": "https://example.com", "name": "a\x00b"},
        ),
        "name",
    )


async def test_upload_name_and_content_type_are_sanitised(
    client: httpx.AsyncClient, world: World
) -> None:
    url = f"{API}/tasks/{world.task.id}/attachments"
    long_name = "n" * 300 + ".pdf"
    response = await client.post(
        url,
        headers=world.headers,
        files={"file": (long_name, b"data", "text/html\r\nX-Evil: 1")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert len(body["name"]) == 255 and body["name"].endswith(".pdf")
    # the content type comes from the extension, never from what the client claims
    assert body["content_type"] == "application/pdf"

    empty = await client.post(
        url, headers=world.headers, files={"file": ("a.txt", b"", "text/plain")}
    )
    assert_invalid(empty, "file")
    bad_type = await client.post(
        url, headers=world.headers, files={"file": ("run.exe", b"MZ", "application/x-msdownload")}
    )
    assert bad_type.status_code == 415
    assert bad_type.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_file_name_cleaner_drops_paths_and_control_characters() -> None:
    from app.tasks.details import _clean_file_name, content_type_for

    assert _clean_file_name("a" + chr(0) + "b" + chr(7) + ".txt") == "ab.txt"
    assert _clean_file_name("..\\..\\evil.pdf") == "evil.pdf"
    assert _clean_file_name("   ") == "file"
    assert _clean_file_name(None) == "file"
    assert content_type_for("notes.TXT") == "text/plain"
    assert content_type_for("photo.jpeg") == "image/jpeg"
    assert content_type_for("page.html") == "application/octet-stream"
    assert content_type_for("noext") == "application/octet-stream"


# --- auth and error shape ---------------------------------------------------------------------


async def test_login_rejects_control_characters_and_spaces(client: httpx.AsyncClient) -> None:
    for email in ("a\x00@b.example", "a b@c.example", "a@b.example\n"):
        response = await client.post(
            f"{API}/auth/login", json={"email": email, "password": "whatever"}
        )
        assert_invalid(response, "email")


async def test_database_errors_are_not_500s(client: httpx.AsyncClient, world: World) -> None:
    """A duplicate status name (case-insensitive in the service) still answers 409."""
    url = f"{API}/projects/{world.project.id}/statuses"
    response = await client.post(
        url, headers=world.headers, json={"name": "to do", "category": "todo"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DUPLICATE_STATUS"
