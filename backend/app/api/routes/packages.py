"""Package management routes: CRUD plus file upload/download."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, OwnedPackage
from app.core.config import settings
from app.models.models import Package, PackageFile
from app.schemas.schemas import (
    MessageResponse,
    PackageCreate,
    PackageFileRead,
    PackageRead,
    PackageUpdate,
)
from app.services.storage import FileTooLargeError, storage
from app.services.validation import sanitize_upload_filename

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
def list_packages(db: DbSession, current_user: CurrentUser) -> list[Package]:
    """List all packages owned by the current user."""
    return list(
        db.scalars(
            select(Package)
            .where(Package.owner_id == current_user.id)
            .order_by(Package.created_at.desc())
        )
    )


@router.get("/{package_id}", response_model=PackageRead)
def get_package(package: OwnedPackage) -> Package:
    """Retrieve a single owned package."""
    return package


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

    storage_key = storage.generate_key()
    try:
        size = storage.save(storage_key, file.file, max_bytes=settings.max_file_size)
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds the maximum allowed size",
        ) from exc

    record = PackageFile(
        package_id=package.id,
        filename=safe_filename,
        content_type=file.content_type or "application/octet-stream",
        size=size,
        storage_key=storage_key,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/{package_id}/files/{file_id}/download")
def download_owned_file(
    file_id: int,
    package: OwnedPackage,
    db: DbSession,
) -> FileResponse:
    """Download a file from an owned package."""
    record = db.get(PackageFile, file_id)
    if record is None or record.package_id != package.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )
    return FileResponse(
        storage.path(record.storage_key),
        media_type=record.content_type,
        filename=record.filename,
    )


@router.delete("/{package_id}/files/{file_id}", response_model=MessageResponse)
def delete_file(
    file_id: int,
    package: OwnedPackage,
    db: DbSession,
) -> MessageResponse:
    """Delete a single file from a package."""
    record = db.get(PackageFile, file_id)
    if record is None or record.package_id != package.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )
    storage.delete(record.storage_key)
    db.delete(record)
    db.commit()
    return MessageResponse(detail="File deleted")
