"""Pydantic v2 schemas for request/response validation."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.models import ShareVisibility

# --- Auth / User -----------------------------------------------------------


class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    username: str
    is_active: bool
    is_admin: bool
    storage_quota: int
    created_at: datetime


class AdminUserRead(UserRead):
    """User view for administrators, augmented with current storage usage."""

    storage_used: int = 0


class UserAdminUpdate(BaseModel):
    username: str | None = Field(
        default=None, min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$"
    )
    email: EmailStr | None = None
    is_active: bool | None = None
    is_admin: bool | None = None
    # Per-user storage budget in bytes; 0 = unlimited. Omit to leave unchanged.
    storage_quota: int | None = Field(default=None, ge=0)


class UserPage(BaseModel):
    items: list[AdminUserRead]
    total: int
    limit: int
    offset: int


class BulkQuotaUpdate(BaseModel):
    """Set the same storage quota (bytes; 0 = unlimited) for every user."""

    storage_quota: int = Field(ge=0)


class BulkQuotaResult(BaseModel):
    """How many user rows a bulk quota update affected."""

    updated: int


class ServiceSettingsRead(BaseModel):
    """Non-sensitive runtime configuration for the admin settings view.

    Assembled from an explicit allow-list in the route: the JWT signing secret
    is never included, and connection strings (database, rate-limit store,
    object storage) are reduced to their backend/scheme so no host or embedded
    credential can leak.
    """

    # Core
    app_name: str
    environment: str
    deployment_profile: str
    allow_registration: bool

    # Authentication / tokens
    algorithm: str
    access_token_expire_minutes: int
    share_access_token_expire_minutes: int

    # Database (backend/scheme only — never the DSN or credentials)
    database_backend: str
    db_pool_size: int
    db_max_overflow: int
    db_pool_timeout: int

    # Storage
    storage_backend: str
    obfuscate_storage_names: bool
    max_file_size: int
    max_files_per_package: int
    max_archive_size: int
    max_concurrent_archive_builds: int

    # Quotas (bytes; 0 = unlimited)
    storage_quota_total: int
    storage_quota_per_user: int

    # CORS
    cors_origins: list[str]

    # Rate limiting
    rate_limit_enabled: bool
    rate_limit_backend: str

    # Logging & observability
    log_level: str
    log_format: str
    audit_retention_days: int
    audit_prune_interval_hours: int


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username_or_email: str
    password: str


class AuthConfig(BaseModel):
    allow_registration: bool
    max_file_size: int


class StorageUsage(BaseModel):
    """The signed-in user's current storage consumption and budget (bytes)."""

    storage_used: int
    storage_quota: int


class PasswordChange(BaseModel):
    """Self-service password change; the current password must be provided."""

    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


class PasswordReset(BaseModel):
    """Administrator-initiated password reset for another user."""

    new_password: str = Field(min_length=8, max_length=128)


# --- Packages --------------------------------------------------------------


class PackageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)


class PackageUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)


class PackageFileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    content_type: str
    size: int
    created_at: datetime


class PackageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    files: list[PackageFileRead] = []


class PackageStats(BaseModel):
    """Aggregated share view/download counters for an owned package."""

    views: int
    downloads: int
    file_downloads: dict[int, int] = Field(default_factory=dict)


class PackagePage(BaseModel):
    """A paginated page of the current user's packages."""

    items: list[PackageRead]
    total: int
    limit: int
    offset: int


class DownloadToken(BaseModel):
    """Short-lived token authorising a browser to stream an owner download."""

    token: str


# --- Shares ----------------------------------------------------------------


class ShareCreate(BaseModel):
    visibility: ShareVisibility = ShareVisibility.PUBLIC
    allowed_emails: list[EmailStr] = Field(default_factory=list)


class ShareUpdate(BaseModel):
    visibility: ShareVisibility | None = None
    is_enabled: bool | None = None
    allowed_emails: list[EmailStr] | None = None


class ShareRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    package_id: int
    token: str
    visibility: ShareVisibility
    is_enabled: bool
    created_at: datetime
    allowed_emails: list[EmailStr] = []


# --- Public share access ---------------------------------------------------


class PublicFile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    content_type: str
    size: int


class PublicShareRead(BaseModel):
    token: str
    package_name: str
    package_description: str | None
    visibility: ShareVisibility
    requires_email: bool
    files: list[PublicFile]
    # Opaque, short-lived credential returned by ``/access`` for restricted
    # shares; supplied on download requests in place of the recipient's email.
    download_token: str | None = None


class ShareAccessRequest(BaseModel):
    """Email supplied by a recipient to unlock a restricted share."""

    email: EmailStr


class MessageResponse(BaseModel):
    detail: str


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    action: str
    actor: str | None
    target: str | None
    package_id: int | None
    request_id: str | None
    client_ip: str | None
    detail: dict[str, Any] | None = None

    @field_validator("detail", mode="before")
    @classmethod
    def _parse_detail(cls, value: object) -> object:
        """Parse the stored JSON ``detail`` string into an object."""
        if isinstance(value, str):
            try:
                return json.loads(value)
            except ValueError:
                return None
        return value


class AuditPage(BaseModel):
    items: list[AuditEventRead]
    total: int
    limit: int
    offset: int
    # Configured audit-log retention in days; 0 means events are kept forever.
    retention_days: int
