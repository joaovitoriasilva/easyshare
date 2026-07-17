"""Shared API dependencies (authentication, current user)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, decode_download_token
from app.db.session import get_db
from app.models.models import Package, PackageFile, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
# Same scheme, but non-raising: used by download endpoints that also accept a
# signed download token in the query string, so a plain browser navigation can
# authorise a download without an Authorization header.
optional_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login", auto_error=False
)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    """Resolve the authenticated user from a bearer token."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    subject = decode_access_token(token)
    if subject is None:
        raise credentials_exc
    try:
        user_id = int(subject)
    except ValueError as exc:
        raise credentials_exc from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_exc
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_owned_package(
    package_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> Package:
    """Resolve a package owned by ``current_user``, or raise 404."""
    package = db.get(Package, package_id)
    if package is None or package.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Package not found"
        )
    return package


OwnedPackage = Annotated[Package, Depends(get_owned_package)]


def get_owned_file(
    file_id: int,
    package: OwnedPackage,
    db: DbSession,
) -> PackageFile:
    """Resolve a file that belongs to an owned package, or raise 404."""
    record = db.get(PackageFile, file_id)
    if record is None or record.package_id != package.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )
    return record


OwnedFile = Annotated[PackageFile, Depends(get_owned_file)]


def get_downloadable_package(
    package_id: int,
    db: DbSession,
    token: Annotated[str | None, Query()] = None,
    bearer: Annotated[str | None, Depends(optional_oauth2_scheme)] = None,
) -> Package:
    """Authorise a package download via a Bearer token or a signed download token.

    The signed download token (issued by the ``/download-token`` endpoint) lets
    the browser stream a file or archive with a plain navigation, so large
    downloads are not buffered in memory by the SPA. A normal Bearer token is
    still accepted for API clients. Anything else is reported as 404 so the
    endpoint never reveals whether a package exists.
    """
    owner_id: int | None = None
    if token:
        claims = decode_download_token(token)
        if claims is not None and claims[1] == package_id:
            owner_id = claims[0]
    elif bearer:
        subject = decode_access_token(bearer)
        if subject is not None and subject.isdigit():
            user = db.get(User, int(subject))
            if user is not None and user.is_active:
                owner_id = user.id
    package = db.get(Package, package_id) if owner_id is not None else None
    if package is None or package.owner_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Package not found"
        )
    return package


DownloadablePackage = Annotated[Package, Depends(get_downloadable_package)]


def get_current_admin(current_user: CurrentUser) -> User:
    """Require the authenticated user to be an administrator."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required",
        )
    return current_user


AdminUser = Annotated[User, Depends(get_current_admin)]
