"""Security audit trail: append-only events persisted to the database.

Each call emits a structured ``easyshare.audit`` log line (always) and makes a
best-effort insert into the ``audit_log`` table. The insert uses its own
short-lived session (never the caller's request session), so a persistence
failure can never roll back the request's transaction and a mid-request call
can never prematurely commit the caller's pending work.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import delete
from sqlalchemy.engine import CursorResult
from starlette.requests import Request

from app.core.logging import get_request_id
from app.db.session import SessionLocal
from app.models.models import AuditEvent

logger = logging.getLogger("easyshare.audit")

# Sessionmaker used to persist audit events. Exposed at module level (rather
# than imported at each call site) so tests can point auditing at their isolated
# engine, since record_event no longer receives the request's session.
audit_sessionmaker = SessionLocal


def record_event(
    action: str,
    *,
    request: Request | None = None,
    actor: str | None = None,
    target: str | None = None,
    package_id: int | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Record a security-relevant event to stdout and the ``audit_log`` table.

    Args:
        action: Dotted event name, e.g. ``share.download`` or ``login.failure``.
        request: The current request, used to derive the client IP.
        actor: Who performed the action (``user:<id>``, an email, or ``None``).
        target: What was acted on, e.g. ``share:<token-prefix>``.
        detail: JSON-serialisable extra context.
    """
    client_ip = request.client.host if request and request.client else None
    logger.info(
        action,
        extra={
            "audit": True,
            "actor": actor,
            "target": target,
            "client_ip": client_ip,
            "detail": detail,
        },
    )
    try:
        with audit_sessionmaker() as session:
            session.add(
                AuditEvent(
                    action=action,
                    actor=actor,
                    target=target,
                    package_id=package_id,
                    request_id=get_request_id(),
                    client_ip=client_ip,
                    detail=json.dumps(detail) if detail else None,
                )
            )
            session.commit()
    except Exception:
        logger.exception("audit.persist_failed", extra={"action": action})


def prune_audit_events(retention_days: int) -> int:
    """Delete audit events older than ``retention_days`` and return the count.

    A no-op returning ``0`` when ``retention_days`` is not positive, so the
    caller can pass the (possibly disabled) configured value directly.
    """
    if retention_days <= 0:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    with audit_sessionmaker() as session:
        result = session.execute(
            delete(AuditEvent).where(AuditEvent.created_at < cutoff)
        )
        session.commit()
        return cast("CursorResult[Any]", result).rowcount or 0
