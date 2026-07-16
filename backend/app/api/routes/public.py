"""Public share access routes used by recipients (no authentication)."""

from __future__ import annotations

import io
import zipfile

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.models import PackageFile, Share, ShareVisibility
from app.schemas.schemas import (
    PublicFile,
    PublicShareRead,
    ShareAccessRequest,
)
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


@router.get("/{token}", response_model=PublicShareRead)
def view_share(token: str, db: DbSession) -> PublicShareRead:
    """View share metadata. Files are hidden for restricted shares."""
    share = _get_active_share(db, token)
    requires_email = share.visibility == ShareVisibility.RESTRICTED
    return PublicShareRead(
        token=share.token,
        package_name=share.package.name,
        package_description=share.package.description,
        visibility=share.visibility,
        requires_email=requires_email,
        files=[] if requires_email else _files_payload(share),
    )


@router.post("/{token}/access", response_model=PublicShareRead)
def access_share(
    token: str, payload: ShareAccessRequest, db: DbSession
) -> PublicShareRead:
    """Unlock a restricted share by providing an allowed email address."""
    share = _get_active_share(db, token)
    _authorize_email(share, str(payload.email))
    return PublicShareRead(
        token=share.token,
        package_name=share.package.name,
        package_description=share.package.description,
        visibility=share.visibility,
        requires_email=share.visibility == ShareVisibility.RESTRICTED,
        files=_files_payload(share),
    )


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
    email: str | None = Query(default=None),
) -> StreamingResponse:
    """Download a single file from a share."""
    share = _get_active_share(db, token)
    _authorize_email(share, email)
    record = _resolve_file(share, file_id)
    stream = storage.open_stream(record.storage_key)
    return StreamingResponse(
        stream,  # type: ignore[arg-type]
        media_type=record.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{record.filename}"'
        },
    )


@router.get("/{token}/download")
def download_shared_archive(
    token: str,
    db: DbSession,
    email: str | None = Query(default=None),
    file_ids: list[int] | None = Query(default=None),
) -> StreamingResponse:
    """Download all files, or a selected subset, as a zip archive.

    Recipients may pass ``file_ids`` repeatedly to select specific files;
    when omitted, every file in the package is included.
    """
    share = _get_active_share(db, token)
    _authorize_email(share, email)

    if file_ids:
        selected = [f for f in share.package.files if f.id in set(file_ids)]
    else:
        selected = list(share.package.files)

    if not selected:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matching files to download",
        )

    buffer = io.BytesIO()
    seen_counts: dict[str, int] = {}
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in selected:
            original = file.filename
            count = seen_counts.get(original, 0)
            seen_counts[original] = count + 1
            if count == 0:
                arcname = original
            else:
                stem, dot, ext = original.rpartition(".")
                arcname = (
                    f"{stem} ({count}){dot}{ext}" if dot else f"{original} ({count})"
                )
            archive.write(storage.path(file.storage_key), arcname=arcname)

    buffer.seek(0)
    package_name = share.package.name.replace('"', "")
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{package_name}.zip"'
        },
    )
