"""Package management routes: CRUD plus file upload/download."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession, OwnedFile, OwnedPackage
from app.core.config import settings
from app.core.rate_limit import EXPENSIVE, limiter
from app.models.models import AuditEvent, Package, PackageFile
from app.schemas.schemas import (
    MessageResponse,
    PackageCreate,
    PackageFileRead,
    PackageRead,
    PackageStats,
    PackageUpdate,
)
from app.services.archive import build_archive_download, validate_archive_request
from app.services.quota import total_storage_used, user_storage_used
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

    View and download totals come from a single grouped ``COUNT`` over the
    audit log. Per-file download counts are read straight from each file's
    denormalised ``download_count`` column (kept current on every share
    download), so the endpoint no longer scans and JSON-parses every download
    event.
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

    file_downloads = {
        file_id: count
        for file_id, count in db.execute(
            select(PackageFile.id, PackageFile.download_count).where(
                PackageFile.package_id == package.id,
                PackageFile.download_count > 0,
            )
        )
    }
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

    # The effective write cap is the smallest of the per-file limit and any
    # remaining per-user / instance-wide storage quota (0 = unlimited). Enforcing
    # it as the streaming ``max_bytes`` means an over-quota upload is aborted
    # mid-write instead of being fully written and then rejected.
    limits: list[tuple[int, str]] = [
        (settings.max_file_size, "File exceeds the maximum allowed size")
    ]
    per_user_quota = package.owner.storage_quota
    if per_user_quota > 0:
        remaining_user = per_user_quota - user_storage_used(db, package.owner_id)
        limits.append((remaining_user, "Upload would exceed your storage quota"))
    if settings.storage_quota_total > 0:
        remaining_total = settings.storage_quota_total - total_storage_used(db)
        limits.append(
            (remaining_total, "Upload would exceed the server storage limit")
        )
    cap, cap_message = min(limits, key=lambda item: item[0])
    if cap <= 0:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=cap_message
        )

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
        size = storage.save(record.storage_key, file.file, max_bytes=cap)
    except FileTooLargeError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=cap_message,
        ) from exc

    record.size = size
    db.commit()
    db.refresh(record)
    return record


@router.get("/{package_id}/files/{file_id}/download")
def download_owned_file(record: OwnedFile) -> Response:
    """Download a file from an owned package."""
    return storage.download_response(
        record.storage_key,
        filename=record.filename,
        content_type=record.content_type,
    )


@router.get("/{package_id}/download")
@limiter.limit(EXPENSIVE)
def download_all_files(package: OwnedPackage, request: Request) -> FileResponse:
    """Download every file in an owned package as a single zip archive."""
    files = list(package.files)
    validate_archive_request(files, empty_detail="No files to download")
    return build_archive_download(files, package_name=package.name)


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
