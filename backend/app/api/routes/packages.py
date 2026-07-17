"""Package management routes: CRUD plus file upload/download."""

from __future__ import annotations

import json

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

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
from app.services.archive import build_archive_download
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
    tally as views and ``share.download`` tallies as downloads. The totals come
    from a single grouped ``COUNT`` in the database rather than loading every
    row; only the download events' ``detail`` column is then read to attribute
    per-file counts (from each event's ``file_id`` for single-file downloads or
    ``file_ids`` for archive downloads).
    """
    counts = db.execute(
        select(AuditEvent.action, func.count())
        .where(
            AuditEvent.package_id == package.id,
            AuditEvent.action.in_((*_VIEW_ACTIONS, "share.download")),
        )
        .group_by(AuditEvent.action)
    )
    views = 0
    downloads = 0
    for action, count in counts:
        if action in _VIEW_ACTIONS:
            views += count
        else:
            downloads += count

    file_downloads: dict[int, int] = {}
    details = db.scalars(
        select(AuditEvent.detail).where(
            AuditEvent.package_id == package.id,
            AuditEvent.action == "share.download",
        )
    )
    for detail_json in details:
        if not detail_json:
            continue
        detail = json.loads(detail_json)
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
    return build_archive_download(package.files, package_name=package.name)


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
