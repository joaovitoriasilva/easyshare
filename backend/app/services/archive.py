"""Build a downloadable zip archive from a package's stored files.

Shared by the owner-side ``/packages/{id}/download`` route and the public
``/s/{token}/download`` share route so the temp-file handling, duplicate-name
suffixing and cleanup logic live in exactly one place.
"""

from __future__ import annotations

import os
import tempfile
import zipfile
from collections.abc import Iterable

from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.models.models import PackageFile
from app.services.storage import storage


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
    """
    # Not a context manager (SIM115): the handle outlives this function — it is
    # closed here but streamed and unlinked only after the response is sent.
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)  # noqa: SIM115
    tmp_path = tmp.name
    try:
        seen_counts: dict[str, int] = {}
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as archive:
            for file in files:
                arcname = _unique_arcname(file.filename, seen_counts)
                archive.write(storage.path(file.storage_key), arcname=arcname)
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
