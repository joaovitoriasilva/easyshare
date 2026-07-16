"""Local filesystem storage service for uploaded files."""

from __future__ import annotations

import contextlib
import os
import secrets
import shutil
from pathlib import Path

from app.core.config import settings

# Upper bound for the readable filename component of a storage key, keeping the
# on-disk path within both the ``storage_key`` column (255) and typical
# filesystem per-component limits (NAME_MAX, usually 255 bytes).
_MAX_READABLE_NAME = 150


def _readable_name(file_id: int, filename: str) -> str:
    """Build a collision-free, path-safe ``{file_id}_{filename}`` component.

    The ``file_id`` prefix guarantees uniqueness (so two files sharing a name
    never clash) and neutralises any residual ``..`` name. Path separators are
    stripped defensively so the component can never escape its package
    directory; :meth:`StorageService._resolve` remains the ultimate guard.
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


class StorageService:
    """Stores file contents on the local filesystem under a base directory."""

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

    def save(
        self, storage_key: str, source: object, max_bytes: int | None = None
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
                    chunk = source.read(1024 * 1024)  # type: ignore[attr-defined]
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

    def open_stream(self, storage_key: str) -> object:
        """Open a stored file for reading in binary mode."""
        return self._resolve(storage_key).open("rb")

    def path(self, storage_key: str) -> Path:
        """Return the absolute path for a stored file."""
        return self._resolve(storage_key)

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


storage = StorageService()
