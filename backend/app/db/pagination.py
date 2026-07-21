"""Shared offset/limit pagination for list endpoints.

Every listing route needs the same two things from a query: the total number of
matching rows (so the client can render page controls) and one ``limit``/
``offset`` slice of them. :func:`paginate` centralises that count-plus-slice so
the pattern is not re-implemented per route.
"""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session


def paginate[T](
    db: Session, stmt: Select[tuple[T]], *, limit: int, offset: int
) -> tuple[list[T], int]:
    """Return one page of ``stmt`` plus the total row count of the full query.

    ``total`` counts the query with its ordering stripped (irrelevant to a
    count, and cheaper) while the returned page applies ``limit``/``offset`` to
    the original, ordered statement.
    """
    total = (
        db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
        or 0
    )
    items = list(db.scalars(stmt.limit(limit).offset(offset)))
    return items, total
