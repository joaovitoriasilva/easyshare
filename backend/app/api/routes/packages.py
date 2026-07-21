"""Package management routes: CRUD plus file upload/download."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import func, or_, select

from app.api.deps import (
    CurrentUser,
    DbSession,
    DownloadablePackage,
    OwnedFile,
    OwnedPackage,
)
from app.core.audit import audit_buffer
from app.core.config import settings
from app.core.rate_limit import EXPENSIVE, limiter
from app.core.security import create_download_token
from app.core.utils import as_utc
from app.db.pagination import paginate
from app.models.models import AuditEvent, Package, PackageFile
from app.schemas.schemas import (
    DownloadToken,
    MessageResponse,
    PackageCreate,
    PackageFileRead,
    PackageListItem,
    PackagePage,
    PackageRead,
    PackageStats,
    PackageUpdate,
)
from app.services.archive import build_archive_download, validate_archive_request
from app.services.counters import counter_buffer
from app.services.files import store_package_file
from app.services.quota import (
    QuotaExceededError,
    enforce_quota_after_write,
    remaining_upload_cap,
)
from app.services.storage import FileTooLargeError, storage
from app.services.validation import sanitize_upload_filename

router = APIRouter(prefix="/packages", tags=["packages"])


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so a user's search term is matched literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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


@router.get("", response_model=PackagePage)
def list_packages(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, max_length=255),
) -> PackagePage:
    """List packages owned by the current user, newest first (paginated).

    Each item carries a ``file_count`` computed by a single grouped query rather
    than the full file list, so listing N packages never serialises every file
    of every package (avoids N+1 and large payloads). ``total`` lets the client
    render page controls without fetching every package. An optional ``q``
    filters by a case-insensitive substring of the package name or description.
    """
    filters = [Package.owner_id == current_user.id]
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip())}%"
        filters.append(
            or_(
                Package.name.ilike(pattern, escape="\\"),
                Package.description.ilike(pattern, escape="\\"),
            )
        )
    items, total = paginate(
        db,
        select(Package).where(*filters).order_by(Package.created_at.desc()),
        limit=limit,
        offset=offset,
    )
    # One grouped query yields the file count for just the packages on this page.
    package_ids = [pkg.id for pkg in items]
    counts: dict[int, int] = {}
    if package_ids:
        rows = db.execute(
            select(PackageFile.package_id, func.count())
            .where(PackageFile.package_id.in_(package_ids))
            .group_by(PackageFile.package_id)
        )
        counts = {pid: int(count) for pid, count in rows}
    return PackagePage(
        items=[
            PackageListItem(
                id=pkg.id,
                name=pkg.name,
                description=pkg.description,
                created_at=pkg.created_at,
                updated_at=pkg.updated_at,
                file_count=counts.get(pkg.id, 0),
            )
            for pkg in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{package_id}", response_model=PackageRead)
def get_package(package: OwnedPackage) -> Package:
    """Retrieve a single owned package."""
    return package


@router.get("/{package_id}/stats", response_model=PackageStats)
def get_package_stats(package: OwnedPackage, db: DbSession) -> PackageStats:
    """Aggregate share view/download counters for an owned package.

    Views are read from the share's denormalised ``view_count``; download totals
    (and the most recent download time) come from a single grouped query over
    the audit log. Per-file download counts are read straight from each file's
    denormalised ``download_count`` column (kept current on every share
    download), so the endpoint no longer scans and JSON-parses every download
    event. View and per-file download counters are accumulated in memory and
    flushed to the database in batches, so the still-buffered delta is added
    here to keep the numbers the owner sees near-real-time.
    """
    downloads_count, last_downloaded_at = db.execute(
        select(func.count(), func.max(AuditEvent.created_at)).where(
            AuditEvent.package_id == package.id,
            AuditEvent.action == "share.download",
        )
    ).one()
    # Fold in downloads still buffered in memory (audited at request time but not
    # yet flushed) so the owner sees near-real-time totals, mirroring the view
    # and per-file deltas below. ``last_downloaded_at`` from SQLite may be naive,
    # so normalise both sides to UTC before taking the later of the two.
    pending_downloads, pending_last = audit_buffer.pending_download_stats(package.id)
    downloads_count = (downloads_count or 0) + pending_downloads
    if pending_last is not None:
        last_downloaded_at = (
            pending_last
            if last_downloaded_at is None
            else max(as_utc(last_downloaded_at), pending_last)
        )
    views = package.share.view_count if package.share is not None else 0
    if package.share is not None:
        views += counter_buffer.pending_view(package.share.id)

    file_ids = [file.id for file in package.files]
    persisted = {
        file_id: count
        for file_id, count in db.execute(
            select(PackageFile.id, PackageFile.download_count).where(
                PackageFile.package_id == package.id,
                PackageFile.download_count > 0,
            )
        )
    }
    pending = counter_buffer.pending_downloads(file_ids)
    file_downloads = {
        file_id: total
        for file_id in file_ids
        if (total := persisted.get(file_id, 0) + pending.get(file_id, 0))
    }
    return PackageStats(
        views=views,
        downloads=downloads_count,
        file_downloads=file_downloads,
        last_downloaded_at=last_downloaded_at,
    )


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
    # remaining per-user / instance-wide storage quota (0 = unlimited). It is
    # enforced up front against the upload's known size (below) so a doomed
    # upload never touches the database or storage, and again as the streaming
    # ``max_bytes`` fallback for the rare client that streams without a size.
    cap, cap_message = remaining_upload_cap(db, package)
    # Reject before spending resources: bail out now — before creating the DB
    # row or writing any bytes — if the quota is already exhausted (cap <= 0) or
    # the upload's reported size already exceeds the cap. Starlette has counted
    # the spooled upload into ``file.size`` by the time this handler runs.
    if cap <= 0 or (file.size is not None and file.size > cap):
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=cap_message
        )

    # Persist the row first (without committing) so that, when obfuscation is
    # disabled, the readable storage key can embed the file's database id. In
    # obfuscated mode the provisional random key generated here is already the
    # final one.
    try:
        record = store_package_file(
            db,
            package,
            filename=safe_filename,
            content_type=file.content_type or "application/octet-stream",
            writer=lambda key: storage.save(key, file.file, max_bytes=cap),
        )
    except FileTooLargeError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=cap_message,
        ) from exc

    # Authoritative quota re-check now that the real size is known and the row is
    # flushed: closes the window where concurrent uploads for the same user each
    # pass the up-front check above and together overrun the quota. On failure
    # the stored bytes and the flushed row are both undone.
    try:
        enforce_quota_after_write(db, package)
    except QuotaExceededError as exc:
        storage_key = record.storage_key
        db.rollback()
        storage.delete(storage_key)
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)
        ) from exc

    db.commit()
    db.refresh(record)
    return record


@router.post("/{package_id}/download-token", response_model=DownloadToken)
def create_package_download_token(package: OwnedPackage) -> DownloadToken:
    """Issue a short-lived token to download this package via a plain navigation.

    The SPA fetches a token, then points the browser at the download URL with
    the token in the query string, so files/archives stream to disk instead of
    being buffered in memory behind an Authorization header.
    """
    return DownloadToken(token=create_download_token(package.owner_id, package.id))


@router.get("/{package_id}/files/{file_id}/download")
def download_owned_file(
    file_id: int, package: DownloadablePackage, db: DbSession
) -> Response:
    """Download a single file from an owned package."""
    record = db.get(PackageFile, file_id)
    if record is None or record.package_id != package.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )
    return storage.download_response(
        record.storage_key,
        filename=record.filename,
        content_type=record.content_type,
    )


@router.get("/{package_id}/download")
@limiter.limit(EXPENSIVE)
def download_all_files(
    package: DownloadablePackage,
    request: Request,
    file_ids: list[int] | None = Query(default=None),
) -> StreamingResponse:
    """Download a package as a zip archive.

    Owners may pass ``file_ids`` repeatedly to archive a specific subset;
    omitting it includes every file in the package.
    """
    files = list(package.files)
    if file_ids:
        wanted = set(file_ids)
        files = [file for file in files if file.id in wanted]
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
def delete_all_files(
    package: OwnedPackage,
    db: DbSession,
    file_ids: list[int] | None = Query(default=None),
) -> MessageResponse:
    """Delete files from a package, keeping the package itself.

    Owners may pass ``file_ids`` repeatedly to delete a specific subset;
    omitting it deletes every file in the package.
    """
    wanted = set(file_ids) if file_ids else None
    removed = 0
    for file in list(package.files):
        if wanted is not None and file.id not in wanted:
            continue
        storage.delete(file.storage_key)
        db.delete(file)
        removed += 1
    db.commit()
    return MessageResponse(detail=f"Deleted {removed} file(s)")
