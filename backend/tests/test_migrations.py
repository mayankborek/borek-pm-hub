import asyncio

import asyncpg
from sqlalchemy.engine import make_url

from alembic import command
from alembic.script import ScriptDirectory
from tests.conftest import alembic_config


async def _run(url_text: str, *statements: str) -> list[list[tuple[object, ...]]]:
    url = make_url(url_text)
    connection = await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database=url.database,
    )
    try:
        results = []
        for statement in statements:
            results.append([tuple(row) for row in await connection.fetch(statement)])
        return results
    finally:
        await connection.close()


def test_a_database_at_0011_gets_the_security_migration_when_upgrading(test_db_url: str) -> None:
    """The dev instance sits at 0011, which never ran 0009: the merge revision must add it."""
    config = alembic_config(test_db_url)
    column = """SELECT count(*) FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'token_version'"""
    command.downgrade(config, "base")  # 0009 is a sibling of 0011: only a rebuild leaves it out
    command.upgrade(config, "0011")
    try:
        before = asyncio.run(_run(test_db_url, column))[0]
        command.upgrade(config, "head")
        after = asyncio.run(_run(test_db_url, column))[0]
    finally:
        command.upgrade(config, "head")
    assert (before, after) == ([(0,)], [(1,)])


def test_existing_users_join_the_internal_organisation_when_upgrading(test_db_url: str) -> None:
    config = alembic_config(test_db_url)
    command.downgrade(config, "0014")
    try:
        asyncio.run(
            _run(
                test_db_url,
                "TRUNCATE users CASCADE",
                "INSERT INTO users (name, email, global_role) VALUES ('P', 'p@x', 'pm')",
            )
        )
        command.upgrade(config, "head")
        rows = asyncio.run(
            _run(
                test_db_url,
                """SELECT u.email, o.name, o.type FROM users u
                   JOIN organisations o ON o.id = u.organisation_id""",
            )
        )[0]
    finally:
        command.upgrade(config, "head")
        asyncio.run(_run(test_db_url, "TRUNCATE users, organisations CASCADE"))
    assert rows == [("p@x", "Borek Solutions Group", "internal")]


def test_project_creators_become_leads_when_upgrading(test_db_url: str) -> None:
    """Without this, a PM would lose their projects when PMs are limited to own projects."""
    config = alembic_config(test_db_url)
    wipe = "TRUNCATE project_members, projects, users CASCADE"
    command.downgrade(config, "0012")
    try:
        asyncio.run(
            _run(
                test_db_url,
                wipe,
                """INSERT INTO users (id, name, email, global_role) VALUES
                   ('00000000-0000-4000-8000-0000000000a1', 'P', 'p@x', 'pm'),
                   ('00000000-0000-4000-8000-0000000000a2', 'D', 'd@x', 'developer')""",
                """INSERT INTO projects (id, code, name, created_by) VALUES
                   ('00000000-0000-4000-8000-0000000000b1', 'NOMEMBER', 'n',
                    '00000000-0000-4000-8000-0000000000a1'),
                   ('00000000-0000-4000-8000-0000000000b2', 'PLAIN', 'n',
                    '00000000-0000-4000-8000-0000000000a1'),
                   ('00000000-0000-4000-8000-0000000000b3', 'BYDEV', 'n',
                    '00000000-0000-4000-8000-0000000000a2')""",
                """INSERT INTO project_members (project_id, user_id, project_role) VALUES
                   ('00000000-0000-4000-8000-0000000000b2',
                    '00000000-0000-4000-8000-0000000000a1', 'developer')""",
            )
        )
        command.upgrade(config, "head")
        rows = asyncio.run(
            _run(
                test_db_url,
                """SELECT p.code, m.project_role FROM project_members m
                   JOIN projects p ON p.id = m.project_id ORDER BY p.code""",
            )
        )[0]
    finally:
        command.upgrade(config, "head")
        asyncio.run(_run(test_db_url, wipe))
    assert rows == [("NOMEMBER", "project_lead"), ("PLAIN", "project_lead")]


def test_models_and_migrations_are_in_sync(test_db_url: str) -> None:
    """Fails if a model changed without a new Alembic migration."""
    command.check(alembic_config(test_db_url))


def test_there_is_exactly_one_migration_head(test_db_url: str) -> None:
    """Two branches that both add a migration after the same one leave two heads, and then
    `alembic upgrade head` (run when the app starts) refuses to run. If this fails, create a
    merge migration: `alembic merge -m "merge heads" <head1> <head2>`."""
    heads = ScriptDirectory.from_config(alembic_config(test_db_url)).get_heads()
    assert len(heads) == 1, f"several migration heads: {heads}"
