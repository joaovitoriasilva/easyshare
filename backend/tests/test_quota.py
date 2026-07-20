"""Tests for storage quota accounting and the instance-total cache."""

from __future__ import annotations

from app.models.models import Package, PackageFile, User
from app.services import quota
from sqlalchemy.orm import sessionmaker


def test_total_storage_used_caches_within_ttl(db_sessionmaker: sessionmaker) -> None:
    """The instance total is memoised (and exactly rescannable on demand)."""
    with db_sessionmaker() as db:
        user = User(email="a@example.com", username="a", hashed_password="x")
        db.add(user)
        db.flush()
        package = Package(owner_id=user.id, name="p")
        db.add(package)
        db.flush()
        db.add(
            PackageFile(
                package_id=package.id, filename="a", size=100, storage_key="k1"
            )
        )
        db.commit()

        # First cached read scans and memoises 100.
        assert quota.total_storage_used(db, use_cache=True) == 100

        db.add(
            PackageFile(
                package_id=package.id, filename="b", size=50, storage_key="k2"
            )
        )
        db.commit()

        # Within the TTL the stale value is served; an exact read is truthful.
        assert quota.total_storage_used(db, use_cache=True) == 100
        assert quota.total_storage_used(db, use_cache=False) == 150

        # Resetting the cache forces a rescan.
        quota.reset_total_usage_cache()
        assert quota.total_storage_used(db, use_cache=True) == 150


def test_user_storage_used_is_scoped_to_owner(db_sessionmaker: sessionmaker) -> None:
    with db_sessionmaker() as db:
        owner = User(email="o@example.com", username="o", hashed_password="x")
        other = User(email="p@example.com", username="p", hashed_password="x")
        db.add_all([owner, other])
        db.flush()
        mine = Package(owner_id=owner.id, name="mine")
        theirs = Package(owner_id=other.id, name="theirs")
        db.add_all([mine, theirs])
        db.flush()
        db.add(
            PackageFile(package_id=mine.id, filename="a", size=42, storage_key="m1")
        )
        db.add(
            PackageFile(package_id=theirs.id, filename="b", size=99, storage_key="t1")
        )
        db.commit()

        assert quota.user_storage_used(db, owner.id) == 42
