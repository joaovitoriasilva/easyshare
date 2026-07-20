"""Small, dependency-light helpers shared across the application.

Kept in ``core`` (rather than a service) so any layer can import them without a
layering inversion. Currently: UTC normalisation of possibly-naive datetimes
(SQLite stores naive values) and canonical email normalisation used wherever an
address is compared, hashed or de-duplicated.
"""

from __future__ import annotations

from datetime import UTC, datetime


def as_utc(value: datetime) -> datetime:
    """Interpret a possibly-naive datetime as UTC.

    SQLite returns naive datetimes; treating a stored value as UTC keeps
    comparisons against an aware ``datetime.now(UTC)`` from raising. An
    already-aware value is returned unchanged.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def normalize_email(email: str) -> str:
    """Return the canonical form of an email address for comparison/hashing.

    Trims surrounding whitespace and lower-cases the address so the allow-list,
    verification-code hashing and de-duplication all agree on a single form.
    """
    return email.strip().lower()
