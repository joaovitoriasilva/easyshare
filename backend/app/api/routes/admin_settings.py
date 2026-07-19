"""Administrator read-only view of the service's non-sensitive configuration."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AdminUser
from app.core.config import settings
from app.schemas.schemas import ServiceSettingsRead

router = APIRouter(prefix="/admin/settings", tags=["admin"])


def _scheme(uri: str) -> str:
    """Return only the scheme of a connection URI, dropping host/credentials.

    ``postgresql+psycopg://user:pass@host/db`` becomes ``postgresql+psycopg``;
    an empty value (no ``://``) yields an empty string. This is what lets the
    settings view reveal the *backend in use* without ever exposing a host,
    username or password embedded in the URI.
    """
    return uri.split("://", 1)[0].strip().lower() if "://" in uri else ""


@router.get("", response_model=ServiceSettingsRead)
def get_service_settings(admin: AdminUser) -> ServiceSettingsRead:
    """Expose non-sensitive runtime configuration (administrators only).

    The response is built field by field from an allow-list rather than dumping
    the whole settings object, so security-critical values can never leak: the
    JWT signing secret (``secret_key``) is omitted entirely, and every
    connection string is reduced to its backend/scheme via :func:`_scheme`.
    """
    return ServiceSettingsRead(
        app_name=settings.app_name,
        environment=settings.environment,
        deployment_profile=settings.deployment_profile,
        allow_registration=settings.allow_registration,
        algorithm=settings.algorithm,
        access_token_expire_minutes=settings.access_token_expire_minutes,
        share_access_token_expire_minutes=settings.share_access_token_expire_minutes,
        database_backend=_scheme(settings.database_url) or "unknown",
        db_pool_size=settings.db_pool_size,
        db_max_overflow=settings.db_max_overflow,
        db_pool_timeout=settings.db_pool_timeout,
        storage_backend=_scheme(settings.storage_uri) or "local",
        obfuscate_storage_names=settings.obfuscate_storage_names,
        max_file_size=settings.max_file_size,
        max_files_per_package=settings.max_files_per_package,
        max_archive_size=settings.max_archive_size,
        max_concurrent_archive_builds=settings.max_concurrent_archive_builds,
        storage_quota_total=settings.storage_quota_total,
        storage_quota_per_user=settings.storage_quota_per_user,
        cors_origins=list(settings.cors_origins),
        rate_limit_enabled=settings.rate_limit_enabled,
        rate_limit_backend=_scheme(settings.rate_limit_storage_uri) or "memory",
        log_level=settings.log_level,
        log_format=settings.log_format,
        audit_retention_days=settings.audit_retention_days,
        audit_prune_interval_hours=settings.audit_prune_interval_hours,
    )
