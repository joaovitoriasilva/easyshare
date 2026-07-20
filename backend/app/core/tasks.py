"""Background maintenance tasks started and stopped by the app lifespan."""

from __future__ import annotations

import asyncio
import logging

from app.core.audit import prune_audit_events
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


async def counter_flush_loop() -> None:
    """Periodically flush buffered view/download counters to the database.

    Public view/download increments are accumulated in memory (see
    ``app/services/counters.py``) to avoid a per-hit ``UPDATE`` + commit on a
    single hot row. This loop drains the buffer every
    ``counter_flush_interval_seconds`` seconds, offloading the blocking write to
    a worker thread so the event loop is never blocked. It is cancelled by the
    application lifespan on shutdown, which performs one final flush.
    """
    interval = settings.counter_flush_interval_seconds
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(counter_buffer.flush)
        except Exception:
            logger.exception("counters.flush_failed")


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
