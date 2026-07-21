"""Security audit trail: append-only events persisted to the database.

Two write paths share one log format:

- :func:`record_event` emits the structured ``easyshare.audit`` log line and
  synchronously inserts the row using its own short-lived session (never the
  caller's request session), so a persistence failure can never roll back the
  request's transaction and a mid-request call can never prematurely commit the
  caller's pending work. Used wherever immediate durability matters.
- :func:`enqueue_event` emits the same log line but queues the row in
  :data:`audit_buffer` for a batched insert by the background flusher, keeping
  the per-hit ``INSERT`` + commit off the request's critical path. Used only on
  the high-frequency share-download paths; the event's timestamp, actor and
  request id are captured at enqueue time, so a download is still audited as an
  attempt (before the file streams), just persisted a moment later.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import delete
from sqlalchemy.engine import CursorResult
from starlette.requests import Request

from app.core.logging import get_request_id, mask_email
from app.db.session import SessionLocal
from app.models.models import AuditEvent

logger = logging.getLogger("easyshare.audit")

# Sessionmaker used to persist audit events. Exposed at module level (rather
# than imported at each call site) so tests can point auditing at their isolated
# engine, since record_event no longer receives the request's session.
audit_sessionmaker = SessionLocal


def _redact(value: str | None) -> str | None:
    """Mask an email-like value for log output; pass anything else through."""
    if value and "@" in value:
        return mask_email(value)
    return value


def _redact_detail(detail: dict[str, Any] | None) -> dict[str, Any] | None:
    """Mask any email-like string values in a detail dict for log output."""
    if not detail:
        return detail
    return {
        key: (_redact(value) if isinstance(value, str) else value)
        for key, value in detail.items()
    }


def _log_event(
    action: str,
    *,
    actor: str | None,
    target: str | None,
    client_ip: str | None,
    detail: dict[str, Any] | None,
) -> None:
    """Emit the structured stdout audit line (emails masked).

    Emails are masked here because stdout is often shipped to external
    aggregators; the full value is kept only in the access-controlled,
    retention-bounded ``audit_log`` table for forensic use.
    """
    logger.info(
        action,
        extra={
            "audit": True,
            "actor": _redact(actor),
            "target": target,
            "client_ip": client_ip,
            "detail": _redact_detail(detail),
        },
    )


def record_event(
    action: str,
    *,
    request: Request | None = None,
    actor: str | None = None,
    target: str | None = None,
    package_id: int | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Log and synchronously persist a security-relevant event.

    Args:
        action: Dotted event name, e.g. ``login.failure`` or ``share.enable``.
        request: The current request, used to derive the client IP.
        actor: Who performed the action (``user:<id>``, an email, or ``None``).
        target: What was acted on, e.g. ``share:<token-prefix>``.
        detail: JSON-serialisable extra context.
    """
    client_ip = request.client.host if request and request.client else None
    _log_event(
        action, actor=actor, target=target, client_ip=client_ip, detail=detail
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


class AuditBuffer:
    """Thread-safe queue of audit events awaiting a coalesced, batched insert.

    High-frequency events (share downloads, which a viral link can generate in a
    burst) are captured here at request time and persisted together by the
    background flusher, keeping the per-hit ``INSERT`` + commit off the request's
    critical path. Losing an unflushed batch to a crash drops those rows from the
    forensic table only — the stdout audit line was already emitted by
    :func:`enqueue_event` — the same time-bounded trade-off the counter buffer
    makes for download analytics.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: list[dict[str, Any]] = []

    def add(self, event: dict[str, Any]) -> None:
        """Queue one captured event payload for the next flush."""
        with self._lock:
            self._pending.append(event)

    def pending_download_stats(
        self, package_id: int
    ) -> tuple[int, datetime | None]:
        """Return the count and latest timestamp of buffered downloads for a package.

        Lets owner-facing stats fold in ``share.download`` events that are
        captured but not yet flushed, mirroring the counter buffer's pending
        deltas so the numbers stay near-real-time. Timestamps are the aware
        values captured at enqueue time.
        """
        with self._lock:
            timestamps = [
                event["created_at"]
                for event in self._pending
                if event["action"] == "share.download"
                and event["package_id"] == package_id
            ]
        if not timestamps:
            return 0, None
        return len(timestamps), max(timestamps)

    def _drain(self) -> list[dict[str, Any]]:
        with self._lock:
            drained = self._pending
            self._pending = []
            return drained

    def flush(self) -> None:
        """Insert all queued events in a single transaction.

        On failure the drained payloads are re-queued (ahead of any newer ones)
        so they are retried on the next flush rather than lost. Because the whole
        batch commits atomically, a failure never partially applies, so
        re-queuing cannot duplicate a row.
        """
        pending = self._drain()
        if not pending:
            return
        try:
            with audit_sessionmaker() as session:
                session.add_all([AuditEvent(**event) for event in pending])
                session.commit()
        except Exception:
            with self._lock:
                self._pending = pending + self._pending
            logger.exception("audit.flush_failed")

    def reset(self) -> None:
        """Discard all queued events (used between tests)."""
        with self._lock:
            self._pending.clear()


audit_buffer = AuditBuffer()


def enqueue_event(
    action: str,
    *,
    request: Request | None = None,
    actor: str | None = None,
    target: str | None = None,
    package_id: int | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Log a high-frequency event now and queue its row for a batched insert.

    Same intent as :func:`record_event`, but instead of inserting inline it emits
    the stdout audit line immediately and hands the row to :data:`audit_buffer`.
    The timestamp, actor, request id and client IP are all captured here, at
    request time, so a share download is audited as an *attempt* (before the file
    streams) even though the row lands a moment later via the background flusher.
    Reserved for the hot download paths; every other call site uses the
    immediately-durable :func:`record_event`.
    """
    client_ip = request.client.host if request and request.client else None
    _log_event(
        action, actor=actor, target=target, client_ip=client_ip, detail=detail
    )
    audit_buffer.add(
        {
            "action": action,
            "actor": actor,
            "target": target,
            "package_id": package_id,
            "request_id": get_request_id(),
            "client_ip": client_ip,
            "created_at": datetime.now(UTC),
            "detail": json.dumps(detail) if detail else None,
        }
    )


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
