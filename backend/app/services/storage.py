"""Pluggable blob storage for uploaded files.

The active backend is chosen from ``EASYSHARE_STORAGE_URI`` by
:func:`build_storage`: an empty value (the default) keeps files on local disk
under ``storage_dir``; an ``s3://…`` URI stores them in S3-compatible object
storage. Domain code depends only on the :class:`StorageBackend` interface, so
switching backends needs no code changes and no data migration (the database
only ever stores the opaque storage key).
"""

from __future__ import annotations

import contextlib
import os
import secrets
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote

from fastapi.responses import FileResponse
from starlette.responses import Response

from app.core.config import settings

# Upper bound for the readable filename component of a storage key, keeping the
# on-disk path within both the ``storage_key`` column (255) and typical
# filesystem per-component limits (NAME_MAX, usually 255 bytes).
_MAX_READABLE_NAME = 150


def content_disposition_attachment(filename: str) -> str:
    """Build a ``Content-Disposition: attachment`` header value for ``filename``.

    Mirrors Starlette's ``FileResponse`` handling: a plain quoted ``filename``
    for names that need no escaping, and the RFC 5987 ``filename*`` form when the
    name contains characters that must be percent-encoded. Shared by the archive
    builder and the S3 backend so the rule lives in exactly one place.
    """
    quoted = quote(filename)
    if quoted == filename:
        return f'attachment; filename="{filename}"'
    return f"attachment; filename*=utf-8''{quoted}"


def _readable_name(file_id: int, filename: str) -> str:
    """Build a collision-free, path-safe ``{file_id}_{filename}`` component.

    The ``file_id`` prefix guarantees uniqueness (so two files sharing a name
    never clash) and neutralises any residual ``..`` name. Path separators are
    stripped defensively so the component can never escape its package
    directory; :meth:`LocalStorageBackend._resolve` remains the ultimate guard.
    """
    safe = filename.replace("/", "_").replace("\\", "_")
    stem, ext = os.path.splitext(safe)
    if len(stem) > _MAX_READABLE_NAME:
        stem = stem[:_MAX_READABLE_NAME]
    return f"{file_id}_{stem}{ext}"


class FileTooLargeError(Exception):
    """Raised when an upload exceeds the maximum allowed size mid-stream."""

    def __init__(self, max_bytes: int) -> None:
        super().__init__(
            f"File exceeds the maximum allowed size of {max_bytes} bytes"
        )
        self.max_bytes = max_bytes


class StorageBackend(ABC):
    """Interface every storage backend implements.

    Storage-key generation is backend-agnostic and shared here; each concrete
    backend provides persistence, streaming, deletion and download serving.
    """

    def generate_key(self) -> str:
        """Return a unique, opaque storage key."""
        return secrets.token_hex(16)

    def readable_key(self, package_id: int, file_id: int, filename: str) -> str:
        """Return a human-readable ``{package_id}/{file_id}_{filename}`` key.

        Used when ``obfuscate_storage_names`` is disabled so files stay
        browsable on disk. The ``file_id`` makes the key unique, so the row
        must be flushed (to assign its id) before calling.
        """
        return f"{package_id}/{_readable_name(file_id, filename)}"

    @abstractmethod
    def save(
        self, storage_key: str, source: BinaryIO, max_bytes: int | None = None
    ) -> int:
        """Persist ``source`` and return the number of bytes stored.

        Raises:
            FileTooLargeError: If the stream exceeds ``max_bytes``.
        """

    @abstractmethod
    def open_stream(self, storage_key: str) -> BinaryIO:
        """Open a stored object for reading in binary mode."""

    @abstractmethod
    def delete(self, storage_key: str) -> None:
        """Delete a stored object; a missing object is not an error."""

    @abstractmethod
    def exists(self, storage_key: str) -> bool:
        """Return whether an object exists for ``storage_key``."""

    @abstractmethod
    def check_writable(self) -> None:
        """Verify the backend is reachable and writable.

        Used by the readiness probe. Raises ``OSError`` when the backing store
        cannot be written to, so a detached volume or unreachable bucket is
        reported as not-ready instead of silently failing uploads.
        """

    @abstractmethod
    def download_response(
        self, storage_key: str, *, filename: str, content_type: str
    ) -> Response:
        """Return a response that delivers the object as a download.

        Local storage streams the file directly (zero-copy, range-capable);
        object storage redirects to a short-lived presigned URL so the object
        is served by the store/CDN rather than proxied through this process.
        """


class LocalStorageBackend(StorageBackend):
    """Stores object contents as files on the local filesystem."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = Path(base_dir or settings.storage_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, storage_key: str) -> Path:
        """Resolve a storage key to an absolute path, preventing traversal."""
        target = (self.base_dir / storage_key).resolve()
        base = self.base_dir.resolve()
        if base != target and base not in target.parents:
            raise ValueError("Invalid storage key")
        return target

    def save(
        self, storage_key: str, source: BinaryIO, max_bytes: int | None = None
    ) -> int:
        """Persist a file-like ``source`` and return the number of bytes written.

        When ``max_bytes`` is provided, the write is aborted as soon as the
        limit is exceeded and the partial file is removed, so oversized uploads
        are never fully written to disk.

        Raises:
            FileTooLargeError: If the stream exceeds ``max_bytes``.
        """
        target = self._resolve(storage_key)
        # Readable storage keys nest files under a per-package subdirectory.
        target.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        try:
            with target.open("wb") as buffer:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if max_bytes is not None and size > max_bytes:
                        raise FileTooLargeError(max_bytes)
                    buffer.write(chunk)
        except FileTooLargeError:
            target.unlink(missing_ok=True)
            raise
        return size

    def open_stream(self, storage_key: str) -> BinaryIO:
        """Open a stored file for reading in binary mode."""
        return self._resolve(storage_key).open("rb")

    def path(self, storage_key: str) -> Path:
        """Return the absolute path for a stored file."""
        return self._resolve(storage_key)

    def exists(self, storage_key: str) -> bool:
        return self._resolve(storage_key).is_file()

    def check_writable(self) -> None:
        """Verify the storage directory exists and is writable."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        probe = self.base_dir / f".healthcheck-{secrets.token_hex(8)}"
        try:
            probe.write_bytes(b"")
        finally:
            probe.unlink(missing_ok=True)

    def download_response(
        self, storage_key: str, *, filename: str, content_type: str
    ) -> Response:
        return FileResponse(
            self.path(storage_key), media_type=content_type, filename=filename
        )

    def delete(self, storage_key: str) -> None:
        """Delete a stored file, pruning an emptied package subdirectory."""
        target = self._resolve(storage_key)
        if target.exists():
            target.unlink()
        # Remove the now-empty package subdirectory left by readable storage
        # keys; never touch the base directory itself.
        parent = target.parent
        if parent != self.base_dir.resolve():
            # Only succeeds when the directory is empty; ignore otherwise.
            with contextlib.suppress(OSError):
                parent.rmdir()

    def reset(self) -> None:
        """Remove all stored files (used in tests)."""
        if self.base_dir.exists():
            shutil.rmtree(self.base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)


def build_storage() -> StorageBackend:
    """Build the storage backend selected by ``settings.storage_uri``.

    An empty URI (the default) or a ``local://path`` URI uses the local
    filesystem; an ``s3://bucket/prefix`` URI uses object storage. The S3
    backend is imported lazily so a default deployment never imports boto3.

    Raises:
        ValueError: When the URI uses an unsupported scheme.
    """
    uri = settings.storage_uri.strip()
    if not uri:
        return LocalStorageBackend(settings.storage_dir)
    scheme, _, rest = uri.partition("://")
    scheme = scheme.lower()
    if scheme == "local":
        return LocalStorageBackend(Path(rest) if rest else settings.storage_dir)
    if scheme == "s3":
        from app.services.storage_s3 import S3StorageBackend

        return S3StorageBackend.from_uri(uri)
    raise ValueError(f"Unsupported EASYSHARE_STORAGE_URI scheme: {scheme or uri!r}")


storage: StorageBackend = build_storage()
