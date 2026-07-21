"""SQLAlchemy ORM models for EasyShare."""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _default_storage_quota() -> int:
    """Per-user storage budget for a new account, from the current config."""
    return settings.storage_quota_per_user


class ShareVisibility(str, enum.Enum):
    """Whether a share is open to anyone or limited to specific emails."""

    PUBLIC = "public"
    RESTRICTED = "restricted"


class User(Base):
    """A registered, authenticated user."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    # Consecutive failed-login counter and the time (if any) until which further
    # login attempts are refused. Both are reset on a successful login. They
    # back the account-lockout defence (see app/api/routes/auth.py) and live on
    # the row so the lockout is shared across workers/replicas.
    failed_login_attempts: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Per-user storage budget in bytes, snapshotted from the configured default
    # (``storage_quota_per_user``) when the account is created; 0 means
    # unlimited. Administrators can adjust it per user afterwards.
    storage_quota: Mapped[int] = mapped_column(
        BigInteger, default=_default_storage_quota, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    packages: Mapped[list[Package]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class Package(Base):
    """A collection of one or more files owned by a user."""

    __tablename__ = "packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    owner: Mapped[User] = relationship(back_populates="packages")
    files: Mapped[list[PackageFile]] = relationship(
        back_populates="package", cascade="all, delete-orphan"
    )
    share: Mapped[Share | None] = relationship(
        back_populates="package",
        cascade="all, delete-orphan",
        uselist=False,
    )


class PackageFile(Base):
    """A single stored file belonging to a package."""

    __tablename__ = "package_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    package_id: Mapped[int] = mapped_column(
        ForeignKey("packages.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(255), default="application/octet-stream")
    # BigInteger so a large max_file_size cannot overflow the 32-bit INTEGER
    # limit (~2.1 GB) on databases like PostgreSQL where INTEGER is 4 bytes.
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    # Denormalised download counter, incremented on each share download so the
    # per-file stats can be read in O(files) instead of scanning and JSON-
    # parsing the whole audit log.
    download_count: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    package: Mapped[Package] = relationship(back_populates="files")


class Share(Base):
    """A shareable link for a package with visibility rules."""

    __tablename__ = "shares"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    package_id: Mapped[int] = mapped_column(
        ForeignKey("packages.id", ondelete="CASCADE"), unique=True, index=True
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    visibility: Mapped[ShareVisibility] = mapped_column(
        Enum(ShareVisibility), default=ShareVisibility.PUBLIC
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Optional expiry: once past, the share behaves as if it were disabled.
    # NULL means the share never expires.
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Denormalised counter of landing-page views. Incremented atomically on each
    # public view so view stats do not require an audit row per (often crawled)
    # hit; see app/api/routes/public.py::view_share.
    view_count: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    package: Mapped[Package] = relationship(back_populates="share")
    allowed_emails: Mapped[list[ShareAllowedEmail]] = relationship(
        back_populates="share", cascade="all, delete-orphan"
    )
    access_codes: Mapped[list[ShareAccessCode]] = relationship(
        back_populates="share", cascade="all, delete-orphan"
    )


class ShareAllowedEmail(Base):
    """An email address allowed to access a restricted share."""

    __tablename__ = "share_allowed_emails"
    __table_args__ = (UniqueConstraint("share_id", "email", name="uq_share_email"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    share_id: Mapped[int] = mapped_column(
        ForeignKey("shares.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), index=True)

    share: Mapped[Share] = relationship(back_populates="allowed_emails")


class ShareAccessCode(Base):
    """A one-time code emailed to verify control of a restricted-share email.

    At most one live code exists per (share, email): requesting a new code
    replaces any previous one. The plaintext code is never stored — only a
    keyed hash — and a bounded ``attempts`` counter caps brute-force guessing.
    """

    __tablename__ = "share_access_codes"
    __table_args__ = (
        UniqueConstraint("share_id", "email", name="uq_share_code_email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    share_id: Mapped[int] = mapped_column(
        ForeignKey("shares.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    share: Mapped[Share] = relationship(back_populates="access_codes")


class UploadSession(Base):
    """A resumable, chunked upload in progress for a package.

    Chunks are appended to a server-side scratch file; ``received`` is the
    authoritative byte offset a client resumes from after a dropped connection
    or a page reload. The row and its scratch file are removed on completion, on
    an explicit abort, or by a background sweep once older than the configured
    TTL, so an abandoned upload cannot leak disk indefinitely.
    """

    __tablename__ = "upload_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Opaque, unguessable id handed to the client (never the sequential row id),
    # so one user cannot probe another's in-progress uploads.
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    package_id: Mapped[int] = mapped_column(
        ForeignKey("packages.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(
        String(255), default="application/octet-stream"
    )
    total_size: Mapped[int] = mapped_column(BigInteger)
    received: Mapped[int] = mapped_column(BigInteger, default=0)
    scratch_key: Mapped[str] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class AuditEvent(Base):
    """An append-only record of a security-relevant action."""

    __tablename__ = "audit_log"

    # Composite/extra indexes for the read paths that filter on several columns
    # at once, complementing the single-column indexes below: (package_id,
    # action) serves the owner-activity and per-package stats queries, and actor
    # serves the admin audit view's "filter by actor" path.
    __table_args__ = (
        Index("ix_audit_log_package_action", "package_id", "action"),
        Index("ix_audit_log_actor", "actor"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    action: Mapped[str] = mapped_column(String(64), index=True)
    package_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    actor: Mapped[str | None] = mapped_column(String(320), nullable=True)
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
