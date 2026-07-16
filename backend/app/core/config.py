"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, populated from the environment or a ``.env`` file."""

    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="EASYSHARE_", extra="ignore"
    )

    # Core
    app_name: str = "EasyShare"
    environment: str = "development"
    debug: bool = False

    # Security
    secret_key: str = Field(
        default="change-me-in-production-this-is-not-secure",
        min_length=16,
        description="Secret used to sign JWT access tokens.",
    )
    access_token_expire_minutes: int = 60 * 24
    algorithm: str = "HS256"

    # Database
    database_url: str = "sqlite:///./easyshare.db"

    # File storage
    storage_dir: Path = Path("./storage")
    max_file_size: int = 100 * 1024 * 1024  # 100 MB per file
    max_files_per_package: int = 50

    # CORS
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, value: object) -> object:
        """Allow a comma-separated string for CORS origins."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()


settings = get_settings()
