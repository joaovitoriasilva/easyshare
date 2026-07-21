"""Background maintenance tasks started and stopped by the app lifespan."""

from __future__ import annotations

import asyncio
import logging

from app.core.audit import audit_buffer, prune_audit_events
from app.core.config import settings
from app.services.chunked import prune_upload_sessions
from app.services.counters import counter_buffer

logger = logging.getLogger("easyshare.tasks")


async def audit_retention_loop() -> None:
    """Periodically delete audit events older than the retention window.

    Runs one prune immediately, then repeats every
    ``audit_prune_interval_hours``. The blocking delete is offloaded to a worker
    thread so the event loop is never blocked, and the loop is cancelled by the
    application lifespan on shutdown.
    """
    interval = settings.audit_prune_interval_hours * 3600
    while True:
        try:
            removed = await asyncio.to_thread(
                prune_audit_events, settings.audit_retention_days
            )
            if removed:
                logger.info(
                    "audit.pruned",
                    extra={
                        "removed": removed,
                        "retention_days": settings.audit_retention_days,
                    },
                )
        except Exception:
            logger.exception("audit.prune_failed")
        await asyncio.sleep(interval)


async def hot_buffer_flush_loop() -> None:
    """Periodically flush the in-memory hot-path buffers to the database.

    Two high-frequency signals are buffered in process memory to keep their
    per-hit writes off the request's critical path: public view/download
    counters (see ``app/services/counters.py``) and share-download audit events
    (see ``app/core/audit.py``). This loop drains both every
    ``counter_flush_interval_seconds`` seconds, offloading the blocking writes to
    a worker thread so the event loop is never blocked. It is cancelled by the
    application lifespan on shutdown, which performs one final flush of each.
    """
    interval = settings.counter_flush_interval_seconds
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(counter_buffer.flush)
        except Exception:
            logger.exception("counters.flush_failed")
        try:
            await asyncio.to_thread(audit_buffer.flush)
        except Exception:
            logger.exception("audit.flush_failed")


async def upload_session_prune_loop() -> None:
    """Periodically remove abandoned resumable-upload sessions and their scratch.

    Sleeps first (so nothing runs at startup or in short-lived test clients),
    then repeats every ``upload_prune_interval_hours``. The blocking delete runs
    in a worker thread; the loop is cancelled by the application lifespan on
    shutdown.
    """
    interval = settings.upload_prune_interval_hours * 3600
    while True:
        await asyncio.sleep(interval)
        try:
            removed = await asyncio.to_thread(
                prune_upload_sessions, settings.upload_session_ttl_hours
            )
            if removed:
                logger.info("uploads.pruned", extra={"removed": removed})
        except Exception:
            logger.exception("uploads.prune_failed")
