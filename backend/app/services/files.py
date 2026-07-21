"""Shared persistence for an uploaded file.

Both the single-shot upload (``POST /packages/{id}/files``) and the resumable
chunked upload's finalisation create a ``PackageFile`` row, give it a storage
key (readable or obfuscated) and stream the bytes into the storage backend.
This helper holds that common sequence so the two call sites cannot drift; each
caller keeps its own transaction/cleanup around it because their rollback needs
differ (a chunked upload must also drop its ``UploadSession`` row).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.models import Package, PackageFile
from app.services.storage import storage

logger = logging.getLogger("easyshare.files")

# Sessionmaker used by the orphaned-blob sweep; overridable in tests, mirroring
# ``chunked.prune_sessionmaker`` and ``audit.audit_sessionmaker``.
orphan_sessionmaker: sessionmaker[Session] = SessionLocal


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


def delete_stored_files(storage_keys: Iterable[str]) -> None:
    """Best-effort delete a batch of stored objects, logging any failure.

    Storage deletes are network round-trips on object storage, so callers hand a
    whole package's (or user's) keys here to run *off* the request's critical
    path — e.g. via ``BackgroundTasks`` once the authoritative database rows are
    already committed as deleted. A single failed delete is logged and skipped
    rather than aborting the batch; the orphaned-blob sweep
    (:func:`prune_orphaned_blobs`) reclaims anything a failure or crash leaves
    behind.
    """
    for storage_key in storage_keys:
        try:
            storage.delete(storage_key)
        except Exception:
            logger.exception(
                "storage.delete_failed", extra={"storage_key": storage_key}
            )


def prune_orphaned_blobs(retention_hours: int) -> int:
    """Delete unreferenced stored objects older than ``retention_hours``.

    Closes the durability gap where a crash between writing an uploaded file's
    bytes and committing its ``package_files`` row — or a best-effort delete that
    never finished — leaves an object on the storage backend that nothing
    references. The set of referenced keys is read first, then storage is
    listed, and an object is removed only when it is both unreferenced *and*
    older than the cutoff. The age guard makes the sweep race-free: a blob being
    written by an in-flight upload (whose row commits moments later) is always
    newer than the cutoff and therefore kept, so it can never be mistaken for an
    orphan. Returns the number of objects removed. A no-op returning ``0`` when
    ``retention_hours`` is not positive, so the caller can pass the (possibly
    disabled) configured value directly.
    """
    if retention_hours <= 0:
        return 0
    cutoff = time.time() - retention_hours * 3600
    with orphan_sessionmaker() as session:
        referenced = set(session.scalars(select(PackageFile.storage_key)))
    # Collect first, then delete: never mutate the backend while iterating it.
    orphans = [
        storage_key
        for storage_key, modified in storage.iter_objects()
        if modified < cutoff and storage_key not in referenced
    ]
    for storage_key in orphans:
        try:
            storage.delete(storage_key)
        except Exception:
            logger.exception(
                "storage.orphan_delete_failed", extra={"storage_key": storage_key}
            )
    return len(orphans)
