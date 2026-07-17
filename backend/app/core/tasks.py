"""Background maintenance tasks started and stopped by the app lifespan."""

from __future__ import annotations

import asyncio
import logging

from app.core.audit import prune_audit_events
from app.core.config import settings

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
