"""Package management routes: CRUD plus file upload/download."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.models.models import Package, PackageFile
from app.schemas.schemas import (
    MessageResponse,
    PackageCreate,
    PackageFileRead,
    PackageRead,
    PackageUpdate,
)
from app.services.storage import storage

router = APIRouter(prefix="/packages", tags=["packages"])


def _get_owned_package(db: DbSession, package_id: int, owner_id: int) -> Package:
    package = db.get(Package, package_id)
    if package is None or package.owner_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Package not found"
        )
    return package


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
def get_package(
    package_id: int, db: DbSession, current_user: CurrentUser
) -> Package:
    """Retrieve a single owned package."""
    return _get_owned_package(db, package_id, current_user.id)


@router.patch("/{package_id}", response_model=PackageRead)
def update_package(
    package_id: int,
    payload: PackageUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> Package:
    """Update package name or description."""
    package = _get_owned_package(db, package_id, current_user.id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(package, field, value)
    db.commit()
    db.refresh(package)
    return package


@router.delete("/{package_id}", response_model=MessageResponse)
def delete_package(
    package_id: int, db: DbSession, current_user: CurrentUser
) -> MessageResponse:
    """Delete a package and all of its stored files."""
    package = _get_owned_package(db, package_id, current_user.id)
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
    package_id: int,
    db: DbSession,
    current_user: CurrentUser,
    file: UploadFile = File(...),
) -> PackageFile:
    """Upload a file into a package."""
    package = _get_owned_package(db, package_id, current_user.id)

    if len(package.files) >= settings.max_files_per_package:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum number of files per package reached",
        )

    storage_key = storage.generate_key()
    size = storage.save(storage_key, file.file)
    if size > settings.max_file_size:
        storage.delete(storage_key)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds the maximum allowed size",
        )

    record = PackageFile(
        package_id=package.id,
        filename=file.filename or "unnamed",
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
    package_id: int,
    file_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> StreamingResponse:
    """Download a file from an owned package."""
    package = _get_owned_package(db, package_id, current_user.id)
    record = db.get(PackageFile, file_id)
    if record is None or record.package_id != package.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )
    stream = storage.open_stream(record.storage_key)
    return StreamingResponse(
        stream,  # type: ignore[arg-type]
        media_type=record.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{record.filename}"'
        },
    )


@router.delete("/{package_id}/files/{file_id}", response_model=MessageResponse)
def delete_file(
    package_id: int,
    file_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> MessageResponse:
    """Delete a single file from a package."""
    package = _get_owned_package(db, package_id, current_user.id)
    record = db.get(PackageFile, file_id)
    if record is None or record.package_id != package.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )
    storage.delete(record.storage_key)
    db.delete(record)
    db.commit()
    return MessageResponse(detail="File deleted")
