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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    package: Mapped[Package] = relationship(back_populates="share")
    allowed_emails: Mapped[list[ShareAllowedEmail]] = relationship(
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


class AuditEvent(Base):
    """An append-only record of a security-relevant action."""

    __tablename__ = "audit_log"

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
