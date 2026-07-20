"""Shared persistence for an uploaded file.

Both the single-shot upload (``POST /packages/{id}/files``) and the resumable
chunked upload's finalisation create a ``PackageFile`` row, give it a storage
key (readable or obfuscated) and stream the bytes into the storage backend.
This helper holds that common sequence so the two call sites cannot drift; each
caller keeps its own transaction/cleanup around it because their rollback needs
differ (a chunked upload must also drop its ``UploadSession`` row).
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import Package, PackageFile
from app.services.storage import storage


def store_package_file(
    db: Session,
    package: Package,
    *,
    filename: str,
    content_type: str,
    writer: Callable[[str], int],
) -> PackageFile:
    """Create a ``PackageFile`` and persist its bytes via ``writer``.

    The row is added and flushed first so that, when storage-name obfuscation is
    disabled, the readable storage key can embed the file's freshly-assigned id;
    in obfuscated mode the provisional random key is already final. ``writer`` is
    then called with the final ``storage_key``: it must stream the content there
    and return the number of bytes stored. A ``FileTooLargeError`` raised by
    ``writer`` propagates unchanged so the caller can roll back and respond.
    """
    record = PackageFile(
        package_id=package.id,
        filename=filename,
        content_type=content_type,
        size=0,
        storage_key=storage.generate_key(),
    )
    db.add(record)
    db.flush()
    if not settings.obfuscate_storage_names:
        record.storage_key = storage.readable_key(package.id, record.id, filename)
    record.size = writer(record.storage_key)
    return record
