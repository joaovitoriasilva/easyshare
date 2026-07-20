"""Serve the built frontend SPA from the backend process.

In the single-image deployment the Vue app is built at image-build time into
``settings.frontend_dir`` and served directly by FastAPI, so there is no
separate nginx/frontend container. This module implements the two pieces that
used to live in nginx config:

- static assets (``/assets/app.js`` etc.) served with their real file, 404 if
  missing;
- everything else falls back to ``index.html`` so client-side vue-router
  routes (e.g. ``/dashboard``) work on a hard refresh.

``_safe_resolve`` guards against path traversal: the requested path is
resolved against the frontend directory and rejected unless the real,
symlink-resolved result still lives inside it.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.core.config import settings

router = APIRouter()


def _safe_resolve(base_dir: Path, untrusted_path: str) -> Path | None:
    """Resolve ``untrusted_path`` inside ``base_dir``, or ``None`` if unsafe."""
    if not untrusted_path or os.path.isabs(untrusted_path):
        return None

    base_real = base_dir.resolve()
    candidate = (base_real / untrusted_path).resolve()

    try:
        candidate.relative_to(base_real)
    except ValueError:
        return None

    if not candidate.is_file():
        return None

    return candidate


def _serve(path: str, cache_control: str) -> FileResponse:
    resolved = _safe_resolve(settings.frontend_dir, path)
    if resolved is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return FileResponse(resolved, headers={"Cache-Control": cache_control})


# Vite emits content-hashed assets under ``/assets/`` whose URL changes whenever
# their content does, so they can be cached forever; the SPA shell must always
# be revalidated so a fresh deploy is picked up on the next load; other unhashed
# public files (favicons, manifest, theme-init.js) get a short cache.
_IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
_REVALIDATE_CACHE = "no-cache"
_SHORT_CACHE = "public, max-age=3600"


@router.get("/{full_path:path}", include_in_schema=False)
def serve_frontend(full_path: str) -> FileResponse:
    """Serve a built frontend asset, falling back to the SPA shell.

    Registered last (after every API router), so any request that matches a
    real API route never reaches here. Requests under ``/api`` that reach this
    point are genuinely unmatched API paths and must 404 rather than fall back
    to the SPA shell.
    """
    if full_path == "api" or full_path.startswith("api/"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    # A path segment with a "." (app.js, favicon.ico, ...) is a concrete asset;
    # anything else is a client-side route, so serve the SPA shell for it.
    if "." in full_path.rsplit("/", 1)[-1]:
        cache_control = (
            _IMMUTABLE_CACHE if full_path.startswith("assets/") else _SHORT_CACHE
        )
        return _serve(full_path, cache_control)
    return _serve("index.html", _REVALIDATE_CACHE)
