"""Owner-side share management routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import DbSession, OwnedPackage
from app.core.audit import record_event
from app.core.security import generate_share_token
from app.models.models import Share, ShareAllowedEmail, ShareVisibility
from app.schemas.schemas import (
    MessageResponse,
    ShareCreate,
    ShareRead,
    ShareUpdate,
)

router = APIRouter(prefix="/packages/{package_id}/share", tags=["shares"])


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
    """Replace the allowed-email list, de-duplicating case-insensitively.

    The collection is reconciled in place: entries that are still wanted are
    kept, unwanted ones are removed and only genuinely new addresses are
    inserted. Clearing and re-adding every entry would make the unit of work
    emit an INSERT for an address that is only deleted later in the same flush,
    tripping the ``(share_id, email)`` unique constraint.
    """
    desired: list[str] = []
    seen: set[str] = set()
    for email in emails:
        normalized = email.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            desired.append(normalized)

    existing = {entry.email: entry for entry in share.allowed_emails}
    for email, entry in existing.items():
        if email not in seen:
            share.allowed_emails.remove(entry)
    for email in desired:
        if email not in existing:
            share.allowed_emails.append(ShareAllowedEmail(email=email))


def _require_restricted_has_emails(share: Share) -> None:
    """Restricted shares must retain at least one allowed email."""
    if share.visibility == ShareVisibility.RESTRICTED and not share.allowed_emails:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Restricted shares require at least one allowed email",
        )


@router.post("", response_model=ShareRead, status_code=status.HTTP_201_CREATED)
def enable_share(
    payload: ShareCreate,
    package: OwnedPackage,
    db: DbSession,
    request: Request,
) -> ShareRead:
    """Enable sharing for a package, generating a valid share id (token)."""
    if package.share is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sharing is already enabled for this package",
        )

    share = Share(
        package_id=package.id,
        token=generate_share_token(),
        visibility=payload.visibility,
        is_enabled=True,
    )
    _apply_emails(share, [str(e) for e in payload.allowed_emails])
    _require_restricted_has_emails(share)
    db.add(share)
    db.commit()
    db.refresh(share)
    record_event(
        db,
        "share.enable",
        request=request,
        actor=f"user:{package.owner_id}",
        target=f"package:{package.id}",
        detail={"visibility": share.visibility.value},
    )
    return _serialize(share)


@router.get("", response_model=ShareRead)
def get_share(package: OwnedPackage) -> ShareRead:
    """Get the current share configuration for a package."""
    if package.share is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sharing is not enabled for this package",
        )
    return _serialize(package.share)


@router.patch("", response_model=ShareRead)
def update_share(
    payload: ShareUpdate,
    package: OwnedPackage,
    db: DbSession,
    request: Request,
) -> ShareRead:
    """Update visibility, enabled state or allowed emails."""
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

    _require_restricted_has_emails(share)

    db.commit()
    db.refresh(share)
    record_event(
        db,
        "share.update",
        request=request,
        actor=f"user:{package.owner_id}",
        target=f"package:{package.id}",
    )
    return _serialize(share)


@router.delete("", response_model=MessageResponse)
def disable_share(
    package: OwnedPackage, db: DbSession, request: Request
) -> MessageResponse:
    """Disable sharing and remove the share link for a package."""
    if package.share is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sharing is not enabled for this package",
        )
    db.delete(package.share)
    db.commit()
    record_event(
        db,
        "share.disable",
        request=request,
        actor=f"user:{package.owner_id}",
        target=f"package:{package.id}",
    )
    return MessageResponse(detail="Sharing disabled")
