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
    # Deployment topology. "local" (the default) is a single process/node:
    # in-memory rate limiting and local-disk storage need no extra services.
    # "distributed" declares multiple workers/replicas, which cannot share
    # process-local state — so the guard below refuses to start unless a shared
    # rate-limit store (Redis) is configured, ensuring limits are enforced
    # across the whole fleet instead of silently per-process.
    deployment_profile: str = "local"

    # Security
    secret_key: str = Field(
        default="change-me-in-production-this-is-not-secure",
        min_length=16,
        description="Secret used to sign JWT access tokens.",
    )
    access_token_expire_minutes: int = 60 * 24
    # Lifetime of the opaque token that authorises restricted-share downloads.
    share_access_token_expire_minutes: int = 30
    algorithm: str = "HS256"
    allow_registration: bool = True

    # Database
    database_url: str = "sqlite:///./easyshare.db"
    # Connection pool sizing, applied only to server databases (PostgreSQL,
    # MySQL, ...); ignored for SQLite, which does not pool the same way. The
    # defaults roughly match the ASGI threadpool that serves the sync routes so
    # concurrent requests do not queue waiting for a free connection.
    db_pool_size: int = Field(default=20, ge=1)
    db_max_overflow: int = Field(default=20, ge=0)
    db_pool_timeout: int = Field(default=30, ge=1)

    # File storage. ``storage_uri`` selects the backend: empty (the default)
    # stores files on local disk under ``storage_dir``; ``s3://bucket/prefix?
    # region=…&endpoint_url=…`` uses S3-compatible object storage instead
    # (requires the ``s3`` extra / boto3). ``local://path`` is also accepted as
    # an explicit form of the disk backend.
    storage_uri: str = ""
    storage_dir: Path = Path("./storage")
    max_file_size: int = 100 * 1024 * 1024  # 100 MB per file
    max_files_per_package: int = 50
    max_archive_size: int = 5 * 1024 * 1024 * 1024  # 5 GiB per zip download
    # Upper bound on how many zip archives may be built concurrently. Each build
    # holds a worker thread for its whole duration, so without a cap a handful
    # of large archive downloads could exhaust the threadpool and stall every
    # other request. Excess requests get 503 (retry) instead of degrading the
    # whole service.
    max_concurrent_archive_builds: int = Field(default=4, ge=1)

    # Storage quotas, in bytes; 0 means unlimited.
    # ``storage_quota_total`` caps the whole instance's on-disk usage (0 =
    # unlimited by default). ``storage_quota_per_user`` is the budget assigned
    # to each user's ``storage_quota`` when their account is created; it
    # defaults to 10 GiB so that open registration cannot fill the disk without
    # bound. Set it to 0 for unlimited. Existing users keep the value
    # snapshotted at creation (backfilled by migration); administrators can
    # change it per user afterwards.
    storage_quota_total: int = Field(default=0, ge=0)
    storage_quota_per_user: int = Field(default=10 * 1024 * 1024 * 1024, ge=0)
    # When enabled (default) stored files are given opaque random names on disk
    # so the filesystem reveals nothing about their origin or contents. Disable
    # to store files under a readable ``{package_id}/{file_id}_{filename}`` path,
    # which keeps them browsable on disk at the cost of exposing the original
    # names. The original filename is always preserved in the database either
    # way, so this only affects the on-disk layout.
    obfuscate_storage_names: bool = True

    # Frontend (single-image deployment: the built Vue SPA is baked into the
    # backend image at this path and served by FastAPI itself; see
    # app/core/static.py). Missing in local dev, where the SPA is instead
    # served by `npm run dev` / Vite on its own port.
    frontend_dir: Path = Path("/app/frontend/dist")

    # CORS
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_storage_uri: str = "memory://"

    # Logging / observability
    log_level: str = "INFO"
    log_format: str = "console"  # "console" (dev) or "json" (production)

    # Audit log retention. When ``audit_retention_days`` is positive a
    # background task periodically deletes audit events older than that many
    # days; 0 (the default) keeps them indefinitely.
    # ``audit_prune_interval_hours`` controls how often that task runs.
    audit_retention_days: int = Field(default=0, ge=0)
    audit_prune_interval_hours: int = Field(default=24, ge=1)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, value: object) -> object:
        """Allow a comma-separated string for CORS origins."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("deployment_profile")
    @classmethod
    def _validate_profile(cls, value: str) -> str:
        """Reject unknown profiles so a typo can't silently run single-node."""
        normalized = value.strip().lower()
        if normalized not in {"local", "distributed"}:
            raise ValueError(
                "EASYSHARE_DEPLOYMENT_PROFILE must be 'local' or 'distributed'"
            )
        return normalized

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
        if problems:
            raise ValueError(
                "Insecure production configuration: " + "; ".join(problems)
            )
        return self

    @model_validator(mode="after")
    def _guard_distributed_shared_state(self) -> Settings:
        """A distributed deployment must not rely on process-local state.

        With more than one worker/replica both the rate-limit store and the
        database must be shared across processes: an in-memory rate-limit store
        is per-process (limits would be multiplied by the process count), and
        SQLite is single-writer and file-local (it cannot be shared between
        replicas). Fail fast on either rather than degrading silently.
        """
        if self.deployment_profile != "distributed":
            return self
        problems: list[str] = []
        rate_limit_uri = self.rate_limit_storage_uri.strip().lower()
        if not rate_limit_uri or rate_limit_uri.startswith("memory://"):
            problems.append(
                "a shared rate-limit store is required: set "
                "EASYSHARE_RATE_LIMIT_STORAGE_URI to a redis:// URI"
            )
        if self.database_url.strip().lower().startswith("sqlite"):
            problems.append(
                "a shared database is required: set EASYSHARE_DATABASE_URL to a "
                "server database such as postgresql+psycopg://... (SQLite "
                "cannot be shared across replicas)"
            )
        if problems:
            raise ValueError(
                "EASYSHARE_DEPLOYMENT_PROFILE=distributed: " + "; ".join(problems)
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
