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
    # "dev" = pick a seeded user (Phase 1). "entra" = Microsoft Entra ID (later).
    auth_mode: Literal["dev", "entra"] = "dev"

    database_url: str = "postgresql+asyncpg://pmhub:change-me@localhost:5432/pmhub"
    db_pool_size: int = 10
    db_max_overflow: int = 5

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
