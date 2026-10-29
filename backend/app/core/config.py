"""Application settings, loaded from environment variables (and a local .env file)."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["local", "test", "staging", "production"] = "local"
    # "dev" = pick a seeded user (local only). "local" = email + password, signed bearer token.
    # "entra" = Microsoft Entra ID (later).
    auth_mode: Literal["dev", "local", "entra"] = "dev"
    # Signs the access tokens of AUTH_MODE=local. At least 32 characters; keep it secret.
    secret_key: str = ""
    access_token_minutes: int = 480
    # Sign-in is blocked for `lockout_minutes` after `max_failed_logins` wrong passwords in a row.
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    # Sign-in attempts per client IP per minute (per worker process); 0 turns the limit off.
    login_rate_limit_per_minute: int = 10
    # True only when the API is reachable through a reverse proxy alone (prod compose): then the
    # client IP is read from X-Forwarded-For instead of the proxy's own address.
    trust_proxy_headers: bool = False

    database_url: str = "postgresql+asyncpg://pmhub:change-me@localhost:5432/pmhub"
    db_pool_size: int = 10
    db_max_overflow: int = 5
    # Queries running longer than this are cancelled by PostgreSQL (protects the pool).
    db_statement_timeout_ms: int = 30000

    # Task attachments (files) are stored in this folder; a Docker volume keeps them.
    upload_dir: str = "uploads"
    max_upload_mb: int = 25

    # Comma-separated list of allowed frontend origins.
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def _forbid_dev_auth_in_production(self) -> Self:
        if self.environment == "production" and self.auth_mode == "dev":
            raise ValueError("AUTH_MODE=dev is not allowed when ENVIRONMENT=production")
        return self

    @model_validator(mode="after")
    def _require_secret_for_local_auth(self) -> Self:
        if self.auth_mode == "local" and len(self.secret_key) < 32:
            raise ValueError("AUTH_MODE=local needs SECRET_KEY with at least 32 characters")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
