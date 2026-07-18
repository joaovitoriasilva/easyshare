"""Build a downloadable zip archive from a package's stored files.

Shared by the owner-side ``/packages/{id}/download`` route and the public
``/s/{token}/download`` share route so the temp-file handling, duplicate-name
suffixing and cleanup logic live in exactly one place.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
import threading
import zipfile
from collections.abc import Iterable

from fastapi import HTTPException, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.core.config import settings
from app.models.models import PackageFile
from app.services.storage import storage

# Bounds how many archives may be built at once. Each build holds a worker
# thread for its full duration (see ``build_archive_download``), so an
# unbounded number of concurrent large downloads could consume the entire
# threadpool and stall every other request. Requests beyond the limit get a
# 503 telling them to retry, which keeps the rest of the API responsive.
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


def build_archive_download(
    files: Iterable[PackageFile], *, package_name: str
) -> FileResponse:
    """Zip ``files`` into a temp file and return a streaming ``FileResponse``.

    The archive uses ``ZIP_STORED`` (uploaded files are usually already
    compressed, so DEFLATE would mostly burn CPU and hold the worker thread for
    negligible savings) and duplicate filenames are suffixed ``name (n).ext``.
    The temporary file is written, closed, streamed by ``FileResponse`` and
    removed by a background task once the response completes, so its lifetime
    deliberately outlives this function.

    A bounded semaphore caps how many builds run concurrently; when the cap is
    reached the request is rejected with 503 rather than piling onto the
    threadpool. The semaphore is held only for the CPU/IO-heavy build phase (it
    is released before returning); the subsequent streaming is handled on the
    event loop and does not occupy a worker thread.
    """
    if not _build_semaphore.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server is busy preparing downloads, please retry shortly",
            headers={"Retry-After": "5"},
        )
    try:
        return _build_archive(files, package_name=package_name)
    finally:
        _build_semaphore.release()


def _build_archive(
    files: Iterable[PackageFile], *, package_name: str
) -> FileResponse:
    # Not a context manager (SIM115): the handle outlives this function — it is
    # closed here but streamed and unlinked only after the response is sent.
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)  # noqa: SIM115
    tmp_path = tmp.name
    try:
        seen_counts: dict[str, int] = {}
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as archive:
            for file in files:
                arcname = _unique_arcname(file.filename, seen_counts)
                # Stream each object through the backend rather than reading a
                # local path, so the same builder serves local-disk and S3
                # storage. ``closing`` covers both a file object and an S3
                # streaming body.
                with (
                    contextlib.closing(storage.open_stream(file.storage_key)) as src,
                    archive.open(arcname, "w") as dest,
                ):
                    shutil.copyfileobj(src, dest)
    except Exception:
        tmp.close()
        os.unlink(tmp_path)
        raise
    tmp.close()

    return FileResponse(
        tmp_path,
        media_type="application/zip",
        filename=f"{_safe_download_name(package_name)}.zip",
        background=BackgroundTask(os.unlink, tmp_path),
    )
