import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_dev_auth_is_rejected_in_production() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production", auth_mode="dev")


def test_dev_auth_is_allowed_locally() -> None:
    settings = Settings(_env_file=None, environment="local", auth_mode="dev")
    assert settings.auth_mode == "dev"


def test_cors_origins_are_split_into_a_list() -> None:
    settings = Settings(_env_file=None, cors_origins="http://a.test, http://b.test")
    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]
