from alembic import command
from tests.conftest import alembic_config


def test_models_and_migrations_are_in_sync(test_db_url: str) -> None:
    """Fails if a model changed without a new Alembic migration."""
    command.check(alembic_config(test_db_url))
