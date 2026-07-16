"""Security audit trail: append-only events persisted to the database.

Each call emits a structured ``easyshare.audit`` log line (always) and makes a
best-effort insert into the ``audit_log`` table. Persistence failures are
swallowed so auditing can never break the request it describes.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session
from starlette.requests import Request

from app.core.logging import get_request_id
from app.models.models import AuditEvent

logger = logging.getLogger("easyshare.audit")


def record_event(
    db: Session,
    action: str,
    *,
    request: Request | None = None,
    actor: str | None = None,
    target: str | None = None,
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
        db.add(
            AuditEvent(
                action=action,
                actor=actor,
                target=target,
                request_id=get_request_id(),
                client_ip=client_ip,
                detail=json.dumps(detail) if detail else None,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("audit.persist_failed", extra={"action": action})
