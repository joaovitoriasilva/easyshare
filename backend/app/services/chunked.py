"""Server-side scratch storage for resumable, chunked uploads.

A chunked upload accumulates bytes in a local scratch file identified by an
opaque ``scratch_key``; the file's length is the authoritative received offset a
client resumes from. When the upload completes, the scratch file is streamed
into the real storage backend (local disk or S3) via :data:`storage` and then
removed. Scratch always lives on the server's local disk (even when the final
backend is object storage), so this needs no append primitive from the backend.

``scratch_dir`` is a module-level default so tests can redirect it to an
isolated temporary directory, mirroring how the storage backend's ``base_dir``
is patched.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.models import UploadSession
from app.services.storage import storage

# Where in-progress chunk data is buffered; overridable in tests.
scratch_dir: Path = settings.storage_dir / "_incoming"

# Sessionmaker used by the background prune sweep; overridable in tests.
prune_sessionmaker: sessionmaker[Session] = SessionLocal


class ChunkOffsetError(Exception):
    """Raised when a chunk is written at an offset other than the current end."""


def _scratch_path(scratch_key: str) -> Path:
    """Resolve a scratch key to a path inside ``scratch_dir`` (no traversal)."""
    base = scratch_dir.resolve()
    target = (base / scratch_key).resolve()
    if target.parent != base:
        raise ValueError("Invalid scratch key")
    return target


def create_scratch() -> str:
    """Create an empty scratch file and return its opaque key."""
    scratch_dir.mkdir(parents=True, exist_ok=True)
    key = secrets.token_hex(16)
    _scratch_path(key).touch()
    return key


def scratch_size(scratch_key: str) -> int:
    """Return the current byte length of a scratch file (0 if missing)."""
    path = _scratch_path(scratch_key)
    return path.stat().st_size if path.is_file() else 0


def append_chunk(scratch_key: str, offset: int, data: bytes) -> int:
    """Append ``data`` at ``offset`` and return the new total size.

    ``offset`` must equal the current file length, so a retried or out-of-order
    chunk cannot corrupt the assembled file. Writing is append-only.

    Raises:
        ChunkOffsetError: If ``offset`` does not match the current size.
    """
    path = _scratch_path(scratch_key)
    current = path.stat().st_size if path.is_file() else 0
    if offset != current:
        raise ChunkOffsetError(
            f"Expected offset {current}, got {offset}"
        )
    with path.open("ab") as buffer:
        buffer.write(data)
    return current + len(data)


def finalize(scratch_key: str, storage_key: str, max_bytes: int | None = None) -> int:
    """Stream the scratch file into ``storage_key`` and return the stored size.

    The scratch file is removed afterwards even if the store write fails, so a
    completed-or-failed upload never leaves scratch behind.
    """
    path = _scratch_path(scratch_key)
    try:
        with path.open("rb") as source:
            return storage.save(storage_key, source, max_bytes=max_bytes)
    finally:
        path.unlink(missing_ok=True)


def discard(scratch_key: str) -> None:
    """Delete a scratch file, ignoring a missing one."""
    _scratch_path(scratch_key).unlink(missing_ok=True)


def prune_upload_sessions(ttl_hours: int) -> int:
    """Delete upload sessions idle longer than ``ttl_hours`` and return the count.

    Each removed session's scratch file is discarded too, so an abandoned upload
    cannot leak disk indefinitely. Uses its own short-lived session, never a
    request session.
    """
    cutoff = datetime.now(UTC) - timedelta(hours=ttl_hours)
    removed = 0
    with prune_sessionmaker() as session:
        stale = session.scalars(
            select(UploadSession).where(UploadSession.updated_at < cutoff)
        ).all()
        for entry in stale:
            discard(entry.scratch_key)
            session.delete(entry)
            removed += 1
        session.commit()
    return removed
