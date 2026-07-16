"""Audit log read endpoints: owner-scoped activity and admin-wide log."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.models.models import AuditEvent, Package
from app.schemas.schemas import AuditEventRead, AuditPage

router = APIRouter(prefix="/audit", tags=["audit"])


def _page(db: Session, conditions: list[Any], limit: int, offset: int) -> AuditPage:
    """Return a paginated, newest-first page of audit events."""
    stmt = select(AuditEvent)
    if conditions:
        stmt = stmt.where(*conditions)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    events = db.scalars(
        stmt.order_by(AuditEvent.id.desc()).limit(limit).offset(offset)
    )
    return AuditPage(
        items=[AuditEventRead.model_validate(event) for event in events],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/mine", response_model=AuditPage)
def my_activity(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None),
    package_id: int | None = Query(default=None),
) -> AuditPage:
    """Audit events for packages/shares owned by the current user."""
    owned = (
        select(Package.id)
        .where(Package.owner_id == current_user.id)
        .scalar_subquery()
    )
    conditions: list[Any] = [AuditEvent.package_id.in_(owned)]
    if action:
        conditions.append(AuditEvent.action == action)
    if package_id is not None:
        conditions.append(AuditEvent.package_id == package_id)
    return _page(db, conditions, limit, offset)


@router.get("", response_model=AuditPage)
def all_activity(
    db: DbSession,
    admin: AdminUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    package_id: int | None = Query(default=None),
) -> AuditPage:
    """The full audit log (administrators only)."""
    conditions: list[Any] = []
    if action:
        conditions.append(AuditEvent.action == action)
    if actor:
        conditions.append(AuditEvent.actor == actor)
    if package_id is not None:
        conditions.append(AuditEvent.package_id == package_id)
    return _page(db, conditions, limit, offset)
