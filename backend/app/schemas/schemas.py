"""Pydantic v2 schemas for request/response validation."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

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
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username_or_email: str
    password: str


class AuthConfig(BaseModel):
    allow_registration: bool


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
