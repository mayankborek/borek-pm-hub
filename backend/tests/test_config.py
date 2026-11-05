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


def test_invite_links_use_the_frontend_url_or_the_first_cors_origin() -> None:
    explicit = Settings(
        _env_file=None, frontend_url=" https://hub.example/ ", cors_origins="http://a"
    )
    fallback = Settings(
        _env_file=None, frontend_url="", cors_origins="http://a.test, http://b.test"
    )
    assert explicit.invite_base_url == "https://hub.example"
    assert fallback.invite_base_url == "http://a.test"
    assert Settings(_env_file=None, frontend_url="", cors_origins="").invite_base_url == ""
