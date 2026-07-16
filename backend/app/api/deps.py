"""Shared API dependencies (authentication, current user)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.models import Package, PackageFile, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

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
