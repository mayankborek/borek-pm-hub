from alembic import command
from alembic.script import ScriptDirectory
from tests.conftest import alembic_config


def test_models_and_migrations_are_in_sync(test_db_url: str) -> None:
    """Fails if a model changed without a new Alembic migration."""
    command.check(alembic_config(test_db_url))


def test_there_is_exactly_one_migration_head(test_db_url: str) -> None:
    """Two branches that both add a migration after the same one leave two heads, and then
    `alembic upgrade head` (run when the app starts) refuses to run. If this fails, create a
    merge migration: `alembic merge -m "merge heads" <head1> <head2>`."""
    heads = ScriptDirectory.from_config(alembic_config(test_db_url)).get_heads()
    assert len(heads) == 1, f"several migration heads: {heads}"
