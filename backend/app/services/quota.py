"""Storage quota accounting and enforcement helpers.

Usage is derived on demand from ``package_files.size`` (the authoritative
record of what is on disk) rather than a separate counter, so it can never
drift from reality. The queries are simple indexed aggregates.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.models import Package, PackageFile


def user_storage_used(db: Session, user_id: int) -> int:
    """Return the total bytes stored across all of a user's packages."""
    total = db.scalar(
        select(func.coalesce(func.sum(PackageFile.size), 0))
        .select_from(PackageFile)
        .join(Package, PackageFile.package_id == Package.id)
        .where(Package.owner_id == user_id)
    )
    return int(total or 0)


def total_storage_used(db: Session) -> int:
    """Return the total bytes stored across the whole instance."""
    total = db.scalar(select(func.coalesce(func.sum(PackageFile.size), 0)))
    return int(total or 0)
