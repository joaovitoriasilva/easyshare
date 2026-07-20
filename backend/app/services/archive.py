"""Stream a downloadable zip archive from a package's stored files.

Shared by the owner-side ``/packages/{id}/download`` route and the public
``/s/{token}/download`` share route so the streaming zip generation and
duplicate-name suffixing live in exactly one place. The archive is produced
incrementally and streamed to the client, so it is never buffered in full (in
memory or on disk) and no worker thread is held for the whole download.
"""

from __future__ import annotations

import contextlib
import threading
import zipfile
from collections.abc import Iterable, Iterator
from typing import BinaryIO, cast

from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.models.models import PackageFile
from app.services.storage import content_disposition_attachment, storage

# Stream each stored file a chunk at a time so a large archive is never held in
# memory (or on disk) in full.
_STREAM_CHUNK_SIZE = 1024 * 1024

# Bounds how many archive downloads may run at once. Streaming keeps any single
# download from holding a worker thread for its whole duration, but a burst of
# concurrent archive downloads would still drive that many simultaneous storage
# reads; capping them keeps archive traffic from crowding out the rest of the
# API. Requests beyond the limit get a 503 telling them to retry. The slot is
# held for the whole streamed response and released when it completes.
_build_semaphore = threading.BoundedSemaphore(
    settings.max_concurrent_archive_builds
)


def validate_archive_request(
    files: list[PackageFile], *, empty_detail: str
) -> None:
    """Reject an archive request that is empty or exceeds the size cap.

    Raises:
        HTTPException: 404 when ``files`` is empty, 413 when their combined
            size exceeds ``max_archive_size``.
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=empty_detail
        )
    if sum(file.size for file in files) > settings.max_archive_size:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="The selected files exceed the maximum archive size",
        )


def _unique_arcname(filename: str, seen_counts: dict[str, int]) -> str:
    """Return a per-archive-unique name, suffixing duplicates ``name (n).ext``."""
    count = seen_counts.get(filename, 0)
    seen_counts[filename] = count + 1
    if count == 0:
        return filename
    stem, dot, ext = filename.rpartition(".")
    return f"{stem} ({count}){dot}{ext}" if dot else f"{filename} ({count})"


def _safe_download_name(name: str) -> str:
    """Sanitise a package name for use as a ``Content-Disposition`` filename."""
    cleaned = "".join(
        ch for ch in name if ch.isprintable() and ch not in '"\\'
    ).strip()
    return cleaned or "package"


def _zip_content_disposition(package_name: str) -> str:
    """Build a ``Content-Disposition`` header value for the archive download."""
    return content_disposition_attachment(f"{_safe_download_name(package_name)}.zip")


class _ZipStreamBuffer:
    """A write-only, unseekable sink that buffers bytes for a generator to emit.

    ``zipfile.ZipFile`` treats a stream that offers ``tell()`` but not ``seek()``
    as unseekable and writes each member with a trailing data descriptor, so the
    archive can be produced strictly forward — never rewinding to patch a header
    — which is exactly what streaming requires. Bytes accumulate until
    :meth:`drain` hands them to the caller.
    """

    def __init__(self) -> None:
        self._chunks: list[bytes] = []
        self._position = 0

    def write(self, data: bytes) -> int:
        self._chunks.append(bytes(data))
        self._position += len(data)
        return len(data)

    def tell(self) -> int:
        return self._position

    def flush(self) -> None:
        """No-op: there is nothing buffered downstream of this sink."""

    def drain(self) -> bytes:
        """Return and clear everything written since the last drain."""
        if not self._chunks:
            return b""
        data = b"".join(self._chunks)
        self._chunks.clear()
        return data


def _iter_archive_bytes(entries: list[tuple[str, str]]) -> Iterator[bytes]:
    """Yield the bytes of a ``ZIP_STORED`` archive of ``(filename, storage_key)``.

    Each stored file is streamed through the storage backend a chunk at a time
    and immediately re-emitted, so neither an individual file nor the finished
    archive is ever held in full. ``ZIP_STORED`` is used because uploaded files
    are usually already compressed, so DEFLATE would mostly burn CPU for
    negligible savings; duplicate names are suffixed ``name (n).ext``.
    """
    sink = _ZipStreamBuffer()
    seen_counts: dict[str, int] = {}
    # ``sink`` is an unseekable, write-only file object; ``zipfile`` only needs
    # write/tell/flush from it, but its type hints demand a full binary IO.
    zip_target = cast("BinaryIO", sink)
    with zipfile.ZipFile(zip_target, "w", zipfile.ZIP_STORED, allowZip64=True) as archive:
        for filename, storage_key in entries:
            arcname = _unique_arcname(filename, seen_counts)
            # ``closing`` covers both a local file object and an S3 streaming
            # body, so the same builder serves every storage backend.
            with (
                contextlib.closing(storage.open_stream(storage_key)) as source,
                archive.open(arcname, "w") as member,
            ):
                # Opening the member wrote its local header into the sink.
                if chunk := sink.drain():
                    yield chunk
                while data := source.read(_STREAM_CHUNK_SIZE):
                    member.write(data)
                    if chunk := sink.drain():
                        yield chunk
            # Closing the member wrote its data descriptor into the sink.
            if chunk := sink.drain():
                yield chunk
    # Closing the archive wrote the central directory into the sink.
    if chunk := sink.drain():
        yield chunk


def _stream_with_release(entries: list[tuple[str, str]]) -> Iterator[bytes]:
    """Stream the archive, releasing the concurrency slot when it finishes.

    The slot is acquired before this generator starts and released here on every
    exit path — normal completion, an error mid-stream, or the generator being
    closed early because the client disconnected.
    """
    try:
        yield from _iter_archive_bytes(entries)
    finally:
        _build_semaphore.release()


def build_archive_download(
    files: Iterable[PackageFile], *, package_name: str
) -> StreamingResponse:
    """Stream ``files`` as a zip archive.

    The archive is generated incrementally and streamed, so it is never buffered
    in full and a worker thread is borrowed only per chunk rather than held for
    the whole build. A bounded semaphore caps how many archive downloads run
    concurrently; past the cap the request is rejected with 503 rather than
    piling more simultaneous storage reads onto the service. The slot is
    released when the stream completes (see :func:`_stream_with_release`).
    """
    # Snapshot the attributes the stream needs while the ORM instances are still
    # attached to a live session; the generator runs later, after the request's
    # session has been closed.
    entries = [(file.filename, file.storage_key) for file in files]
    if not _build_semaphore.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server is busy preparing downloads, please retry shortly",
            headers={"Retry-After": "5"},
        )
    return StreamingResponse(
        _stream_with_release(entries),
        media_type="application/zip",
        headers={"content-disposition": _zip_content_disposition(package_name)},
    )
