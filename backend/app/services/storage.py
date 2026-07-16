"""Local filesystem storage service for uploaded files."""

from __future__ import annotations

import secrets
import shutil
from pathlib import Path

from app.core.config import settings


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
        """Delete a stored file if it exists."""
        target = self._resolve(storage_key)
        if target.exists():
            target.unlink()

    def reset(self) -> None:
        """Remove all stored files (used in tests)."""
        if self.base_dir.exists():
            shutil.rmtree(self.base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)


storage = StorageService()
