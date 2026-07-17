"""Public share access routes used by recipients (no authentication)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import DbSession
from app.core.audit import record_event
from app.core.config import settings
from app.core.rate_limit import SENSITIVE, limiter
from app.core.security import (
    create_share_access_token,
    decode_share_access_token,
)
from app.models.models import PackageFile, Share, ShareVisibility
from app.schemas.schemas import (
    PublicFile,
    PublicShareRead,
    ShareAccessRequest,
)
from app.services.archive import build_archive_download
from app.services.storage import storage

router = APIRouter(prefix="/s", tags=["public"])


def _get_active_share(db: DbSession, token: str) -> Share:
    share = db.scalar(select(Share).where(Share.token == token))
    if share is None or not share.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Share not found"
        )
    return share


def _authorize_email(share: Share, email: str | None) -> None:
    """Ensure ``email`` may access a restricted share; no-op for public shares."""
    if share.visibility == ShareVisibility.PUBLIC:
        return
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This share requires a valid email address",
        )
    allowed = {entry.email for entry in share.allowed_emails}
    if email.strip().lower() not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This email is not allowed to access the share",
        )


def _authorize_download(share: Share, access_token: str | None) -> str | None:
    """Authorize a download request, returning the authorised email (if any).

    Public shares are always downloadable (returns ``None``). Restricted shares
    require the opaque, short-lived token issued by :func:`access_share`; the
    email it certifies is re-checked against the current allow-list so access
    can be revoked by removing the address.
    """
    if share.visibility == ShareVisibility.PUBLIC:
        return None
    email = (
        decode_share_access_token(access_token, share.token)
        if access_token
        else None
    )
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This share requires a valid access token",
        )
    allowed = {entry.email for entry in share.allowed_emails}
    if email.strip().lower() not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This email is not allowed to access the share",
        )
    return email


def _files_payload(share: Share) -> list[PublicFile]:
    return [
        PublicFile(
            id=f.id,
            filename=f.filename,
            content_type=f.content_type,
            size=f.size,
        )
        for f in share.package.files
    ]


def _public_share_read(
    share: Share, *, reveal_files: bool, download_token: str | None = None
) -> PublicShareRead:
    """Build the public view of a share, optionally revealing its file list."""
    return PublicShareRead(
        token=share.token,
        package_name=share.package.name,
        package_description=share.package.description,
        visibility=share.visibility,
        requires_email=share.visibility == ShareVisibility.RESTRICTED,
        files=_files_payload(share) if reveal_files else [],
        download_token=download_token,
    )


@router.get("/{token}", response_model=PublicShareRead)
def view_share(token: str, db: DbSession, request: Request) -> PublicShareRead:
    """View share metadata. Files are hidden for restricted shares."""
    share = _get_active_share(db, token)
    record_event(
        db,
        "share.view",
        request=request,
        target=f"share:{token[:8]}",
        package_id=share.package_id,
    )
    return _public_share_read(
        share, reveal_files=share.visibility != ShareVisibility.RESTRICTED
    )


@router.post("/{token}/access", response_model=PublicShareRead)
@limiter.limit(SENSITIVE)
def access_share(
    request: Request, token: str, payload: ShareAccessRequest, db: DbSession
) -> PublicShareRead:
    """Unlock a restricted share by providing an allowed email address.

    Returns a short-lived ``download_token`` that the recipient supplies on
    subsequent download requests, so their email never travels in a URL.
    """
    share = _get_active_share(db, token)
    email = str(payload.email)
    try:
        _authorize_email(share, email)
    except HTTPException as exc:
        record_event(
            db,
            "share.access.denied",
            request=request,
            actor=email,
            target=f"share:{token[:8]}",
            package_id=share.package_id,
            detail={"status": exc.status_code},
        )
        raise
    record_event(
        db,
        "share.access.granted",
        request=request,
        actor=email,
        target=f"share:{token[:8]}",
        package_id=share.package_id,
    )
    download_token = (
        create_share_access_token(share.token, email.strip().lower())
        if share.visibility == ShareVisibility.RESTRICTED
        else None
    )
    return _public_share_read(share, reveal_files=True, download_token=download_token)


def _resolve_file(share: Share, file_id: int) -> PackageFile:
    for file in share.package.files:
        if file.id == file_id:
            return file
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
    )


@router.get("/{token}/files/{file_id}/download")
def download_shared_file(
    token: str,
    file_id: int,
    db: DbSession,
    request: Request,
    access: str | None = Query(default=None),
) -> FileResponse:
    """Download a single file from a share."""
    share = _get_active_share(db, token)
    try:
        email = _authorize_download(share, access)
    except HTTPException as exc:
        record_event(
            db,
            "share.download.denied",
            request=request,
            target=f"share:{token[:8]}",
            package_id=share.package_id,
            detail={"status": exc.status_code, "file_id": file_id},
        )
        raise
    record = _resolve_file(share, file_id)
    record_event(
        db,
        "share.download",
        request=request,
        actor=email,
        target=f"share:{token[:8]}",
        package_id=share.package_id,
        detail={"file_id": file_id, "filename": record.filename},
    )
    return FileResponse(
        storage.path(record.storage_key),
        media_type=record.content_type,
        filename=record.filename,
    )


@router.get("/{token}/download")
def download_shared_archive(
    token: str,
    db: DbSession,
    request: Request,
    access: str | None = Query(default=None),
    file_ids: list[int] | None = Query(default=None),
) -> FileResponse:
    """Download all files, or a selected subset, as a zip archive.

    Recipients may pass ``file_ids`` repeatedly to select specific files;
    when omitted, every file in the package is included. The archive is written
    to a temporary file (spilling to disk instead of buffering the whole zip in
    memory) and streamed back, then removed once the response is sent.
    """
    share = _get_active_share(db, token)
    try:
        email = _authorize_download(share, access)
    except HTTPException as exc:
        record_event(
            db,
            "share.download.denied",
            request=request,
            target=f"share:{token[:8]}",
            package_id=share.package_id,
            detail={"status": exc.status_code},
        )
        raise

    if file_ids:
        selected = [f for f in share.package.files if f.id in set(file_ids)]
    else:
        selected = list(share.package.files)

    if not selected:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matching files to download",
        )

    if sum(file.size for file in selected) > settings.max_archive_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="The selected files exceed the maximum archive size",
        )

    record_event(
        db,
        "share.download",
        request=request,
        actor=email,
        target=f"share:{token[:8]}",
        package_id=share.package_id,
        detail={"file_ids": [file.id for file in selected], "archive": True},
    )
    return build_archive_download(selected, package_name=share.package.name)
