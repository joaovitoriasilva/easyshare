"""Storage quota accounting and enforcement helpers.

Usage is derived on demand from ``package_files.size`` (the authoritative
record of what is on disk) rather than a separate counter, so it can never
drift from reality. The queries are simple indexed aggregates.

The instance-wide total is additionally served from a short-lived in-process
cache: it scans the whole ``package_files`` table, so under a burst of uploads
recomputing it every time would be wasteful. The cache is a coarse safety net
for the (opt-in) instance cap, so a small, time-bounded overshoot is acceptable;
per-user accounting stays exact.
"""

from __future__ import annotations

import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.models import Package, PackageFile

# How long a scanned instance-wide total may be reused before rescanning.
_TOTAL_USAGE_CACHE_TTL = 10.0  # seconds
# Single-entry cache: {"value": (monotonic_timestamp, bytes)}. A dict (rather
# than a module global reassigned in the function) keeps the update lock-free
# and avoids a ``global`` statement.
_total_usage_cache: dict[str, tuple[float, int]] = {}


def user_storage_used(db: Session, user_id: int) -> int:
    """Return the total bytes stored across all of a user's packages."""
    total = db.scalar(
        select(func.coalesce(func.sum(PackageFile.size), 0))
        .select_from(PackageFile)
        .join(Package, PackageFile.package_id == Package.id)
        .where(Package.owner_id == user_id)
    )
    return int(total or 0)


def total_storage_used(db: Session, *, use_cache: bool = False) -> int:
    """Return the total bytes stored across the whole instance.

    When ``use_cache`` is set, a value scanned within the last
    ``_TOTAL_USAGE_CACHE_TTL`` seconds is reused instead of rescanning the whole
    table. Callers that must be exact (the default) always scan.
    """
    if use_cache:
        cached = _total_usage_cache.get("value")
        if cached is not None and (time.monotonic() - cached[0]) < _TOTAL_USAGE_CACHE_TTL:
            return cached[1]
    total = int(
        db.scalar(select(func.coalesce(func.sum(PackageFile.size), 0))) or 0
    )
    if use_cache:
        _total_usage_cache["value"] = (time.monotonic(), total)
    return total


def reset_total_usage_cache() -> None:
    """Clear the cached instance total (used between tests)."""
    _total_usage_cache.clear()
