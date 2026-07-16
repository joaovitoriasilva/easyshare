"""Package management routes: CRUD plus file upload/download."""

from __future__ import annotations

import json
import os
import tempfile
import zipfile

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from starlette.background import BackgroundTask

from app.api.deps import CurrentUser, DbSession, OwnedFile, OwnedPackage
from app.core.config import settings
from app.models.models import AuditEvent, Package, PackageFile
from app.schemas.schemas import (
    MessageResponse,
    PackageCreate,
    PackageFileRead,
    PackageRead,
    PackageStats,
    PackageUpdate,
)
from app.services.storage import FileTooLargeError, storage
from app.services.validation import sanitize_upload_filename

_VIEW_ACTIONS = ("share.view", "share.access.granted")

router = APIRouter(prefix="/packages", tags=["packages"])


@router.post("", response_model=PackageRead, status_code=status.HTTP_201_CREATED)
def create_package(
    payload: PackageCreate, db: DbSession, current_user: CurrentUser
) -> Package:
    """Create a new (empty) package owned by the current user."""
    package = Package(
        owner_id=current_user.id,
        name=payload.name,
        description=payload.description,
    )
    db.add(package)
    db.commit()
    db.refresh(package)
    return package


@router.get("", response_model=list[PackageRead])
def list_packages(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[Package]:
    """List packages owned by the current user, newest first (paginated).

    ``files`` are eager-loaded with ``selectinload`` so serialising the list
    issues one extra query instead of one per package (avoids N+1).
    """
    return list(
        db.scalars(
            select(Package)
            .where(Package.owner_id == current_user.id)
            .order_by(Package.created_at.desc())
            .options(selectinload(Package.files))
            .limit(limit)
            .offset(offset)
        )
    )


@router.get("/{package_id}", response_model=PackageRead)
def get_package(package: OwnedPackage) -> Package:
    """Retrieve a single owned package."""
    return package


@router.get("/{package_id}/stats", response_model=PackageStats)
def get_package_stats(package: OwnedPackage, db: DbSession) -> PackageStats:
    """Aggregate share view/download counters for an owned package.

    Counts are derived from the audit log: ``share.view``/``share.access.granted``
    tally as views, ``share.download`` tallies as downloads, and per-file
    download counts are summed from each event's ``file_id`` (single-file
    downloads) or ``file_ids`` (archive downloads) detail.
    """
    events = db.scalars(
        select(AuditEvent).where(
            AuditEvent.package_id == package.id,
            AuditEvent.action.in_((*_VIEW_ACTIONS, "share.download")),
        )
    )
    views = 0
    downloads = 0
    file_downloads: dict[int, int] = {}
    for event in events:
        if event.action in _VIEW_ACTIONS:
            views += 1
            continue
        downloads += 1
        detail = json.loads(event.detail) if event.detail else {}
        file_ids = detail.get("file_ids") or (
            [detail["file_id"]] if "file_id" in detail else []
        )
        for file_id in file_ids:
            file_downloads[file_id] = file_downloads.get(file_id, 0) + 1
    return PackageStats(views=views, downloads=downloads, file_downloads=file_downloads)


@router.patch("/{package_id}", response_model=PackageRead)
def update_package(
    payload: PackageUpdate,
    package: OwnedPackage,
    db: DbSession,
) -> Package:
    """Update package name or description."""
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(package, field, value)
    db.commit()
    db.refresh(package)
    return package


@router.delete("/{package_id}", response_model=MessageResponse)
def delete_package(package: OwnedPackage, db: DbSession) -> MessageResponse:
    """Delete a package and all of its stored files."""
    for file in package.files:
        storage.delete(file.storage_key)
    db.delete(package)
    db.commit()
    return MessageResponse(detail="Package deleted")


@router.post(
    "/{package_id}/files",
    response_model=PackageFileRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_file(
    package: OwnedPackage,
    db: DbSession,
    file: UploadFile = File(...),
) -> PackageFile:
    """Upload a file into a package."""
    if len(package.files) >= settings.max_files_per_package:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum number of files per package reached",
        )

    safe_filename = sanitize_upload_filename(file.filename)

    # Persist the row first (without committing) so that, when obfuscation is
    # disabled, the readable storage key can embed the file's database id. In
    # obfuscated mode the provisional random key generated here is already the
    # final one.
    record = PackageFile(
        package_id=package.id,
        filename=safe_filename,
        content_type=file.content_type or "application/octet-stream",
        size=0,
        storage_key=storage.generate_key(),
    )
    db.add(record)
    db.flush()

    if not settings.obfuscate_storage_names:
        record.storage_key = storage.readable_key(
            package.id, record.id, safe_filename
        )

    try:
        size = storage.save(
            record.storage_key, file.file, max_bytes=settings.max_file_size
        )
    except FileTooLargeError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds the maximum allowed size",
        ) from exc

    record.size = size
    db.commit()
    db.refresh(record)
    return record


@router.get("/{package_id}/files/{file_id}/download")
def download_owned_file(record: OwnedFile) -> FileResponse:
    """Download a file from an owned package."""
    return FileResponse(
        storage.path(record.storage_key),
        media_type=record.content_type,
        filename=record.filename,
    )


@router.get("/{package_id}/download")
def download_all_files(package: OwnedPackage) -> FileResponse:
    """Download every file in an owned package as a single zip archive."""
    if not package.files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No files to download"
        )
    if sum(file.size for file in package.files) > settings.max_archive_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="The package exceeds the maximum archive size",
        )

    # Deliberately not a context manager (SIM115): closed then streamed by
    # FileResponse and unlinked in a background task once the response
    # completes (mirrors public.py::download_shared_archive).
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)  # noqa: SIM115
    tmp_path = tmp.name
    try:
        seen_counts: dict[str, int] = {}
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as archive:
            for file in package.files:
                original = file.filename
                count = seen_counts.get(original, 0)
                seen_counts[original] = count + 1
                if count == 0:
                    arcname = original
                else:
                    stem, dot, ext = original.rpartition(".")
                    arcname = (
                        f"{stem} ({count}){dot}{ext}"
                        if dot
                        else f"{original} ({count})"
                    )
                archive.write(storage.path(file.storage_key), arcname=arcname)
    except Exception:
        tmp.close()
        os.unlink(tmp_path)
        raise
    tmp.close()

    safe_name = (
        "".join(ch for ch in package.name if ch.isprintable() and ch not in '"\\').strip()
        or "package"
    )
    return FileResponse(
        tmp_path,
        media_type="application/zip",
        filename=f"{safe_name}.zip",
        background=BackgroundTask(os.unlink, tmp_path),
    )


@router.delete("/{package_id}/files/{file_id}", response_model=MessageResponse)
def delete_file(record: OwnedFile, db: DbSession) -> MessageResponse:
    """Delete a single file from a package."""
    storage.delete(record.storage_key)
    db.delete(record)
    db.commit()
    return MessageResponse(detail="File deleted")


@router.delete("/{package_id}/files", response_model=MessageResponse)
def delete_all_files(package: OwnedPackage, db: DbSession) -> MessageResponse:
    """Delete every file in a package, keeping the package itself."""
    for file in package.files:
        storage.delete(file.storage_key)
        db.delete(file)
    db.commit()
    return MessageResponse(detail="All files deleted")
