"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Placeholder secrets that must never be used in a production deployment.
_INSECURE_SECRET_KEYS = frozenset(
    {
        "change-me-in-production-this-is-not-secure",
        "please-change-me-in-production",
    }
)


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
    allow_registration: bool = True

    # Database
    database_url: str = "sqlite:///./easyshare.db"

    # File storage
    storage_dir: Path = Path("./storage")
    max_file_size: int = 100 * 1024 * 1024  # 100 MB per file
    max_files_per_package: int = 50

    # CORS
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_storage_uri: str = "memory://"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, value: object) -> object:
        """Allow a comma-separated string for CORS origins."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _guard_production_security(self) -> Settings:
        """Fail fast when production is configured with insecure defaults."""
        if not self.is_production:
            return self
        problems: list[str] = []
        if self.secret_key in _INSECURE_SECRET_KEYS or len(self.secret_key) < 32:
            problems.append(
                "EASYSHARE_SECRET_KEY must be a unique value of at least "
                "32 characters"
            )
        if self.debug:
            problems.append("EASYSHARE_DEBUG must be disabled")
        if problems:
            raise ValueError(
                "Insecure production configuration: " + "; ".join(problems)
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()


settings = get_settings()
