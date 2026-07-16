"""Owner-side share management routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.core.security import generate_share_token
from app.models.models import Package, Share, ShareAllowedEmail, ShareVisibility
from app.schemas.schemas import (
    MessageResponse,
    ShareCreate,
    ShareRead,
    ShareUpdate,
)

router = APIRouter(prefix="/packages/{package_id}/share", tags=["shares"])


def _get_owned_package(db: DbSession, package_id: int, owner_id: int) -> Package:
    package = db.get(Package, package_id)
    if package is None or package.owner_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Package not found"
        )
    return package


def _serialize(share: Share) -> ShareRead:
    return ShareRead(
        id=share.id,
        package_id=share.package_id,
        token=share.token,
        visibility=share.visibility,
        is_enabled=share.is_enabled,
        created_at=share.created_at,
        allowed_emails=[entry.email for entry in share.allowed_emails],
    )


def _apply_emails(share: Share, emails: list[str]) -> None:
    """Replace the allowed-email list, de-duplicating case-insensitively."""
    share.allowed_emails.clear()
    seen: set[str] = set()
    for email in emails:
        normalized = email.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            share.allowed_emails.append(ShareAllowedEmail(email=normalized))


@router.post("", response_model=ShareRead, status_code=status.HTTP_201_CREATED)
def enable_share(
    package_id: int,
    payload: ShareCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> ShareRead:
    """Enable sharing for a package, generating a valid share id (token)."""
    package = _get_owned_package(db, package_id, current_user.id)
    if package.share is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sharing is already enabled for this package",
        )
    if payload.visibility == ShareVisibility.RESTRICTED and not payload.allowed_emails:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Restricted shares require at least one allowed email",
        )

    share = Share(
        package_id=package.id,
        token=generate_share_token(),
        visibility=payload.visibility,
        is_enabled=True,
    )
    _apply_emails(share, [str(e) for e in payload.allowed_emails])
    db.add(share)
    db.commit()
    db.refresh(share)
    return _serialize(share)


@router.get("", response_model=ShareRead)
def get_share(
    package_id: int, db: DbSession, current_user: CurrentUser
) -> ShareRead:
    """Get the current share configuration for a package."""
    package = _get_owned_package(db, package_id, current_user.id)
    if package.share is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sharing is not enabled for this package",
        )
    return _serialize(package.share)


@router.patch("", response_model=ShareRead)
def update_share(
    package_id: int,
    payload: ShareUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> ShareRead:
    """Update visibility, enabled state or allowed emails."""
    package = _get_owned_package(db, package_id, current_user.id)
    share = package.share
    if share is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sharing is not enabled for this package",
        )

    if payload.visibility is not None:
        share.visibility = payload.visibility
    if payload.is_enabled is not None:
        share.is_enabled = payload.is_enabled
    if payload.allowed_emails is not None:
        _apply_emails(share, [str(e) for e in payload.allowed_emails])

    if share.visibility == ShareVisibility.RESTRICTED and not share.allowed_emails:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Restricted shares require at least one allowed email",
        )

    db.commit()
    db.refresh(share)
    return _serialize(share)


@router.delete("", response_model=MessageResponse)
def disable_share(
    package_id: int, db: DbSession, current_user: CurrentUser
) -> MessageResponse:
    """Disable sharing and remove the share link for a package."""
    package = _get_owned_package(db, package_id, current_user.id)
    if package.share is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sharing is not enabled for this package",
        )
    db.delete(package.share)
    db.commit()
    return MessageResponse(detail="Sharing disabled")
