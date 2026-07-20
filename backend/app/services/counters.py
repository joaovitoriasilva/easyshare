"""In-memory aggregation of hot public view/download counters.

A public share view and a share download would otherwise each issue an
``UPDATE ... SET counter = counter + 1`` plus a commit against a *single* share
or file row. A viral link therefore serialises thousands of concurrent
transactions on that one row (each holds a row lock until commit), which is the
most likely write hotspot at scale.

Instead, increments are accumulated in process memory and flushed to the
database in batches by a background task (see ``app/core/tasks.py``), coalescing
many per-hit increments into a single ``UPDATE`` per row. Owner-facing reads add
the still-buffered delta so the numbers stay near-real-time. A crash can lose an
unflushed, time-bounded delta, which is acceptable for approximate view/download
analytics — the same trade-off already made by the instance-total quota cache.

``counter_sessionmaker`` is exposed at module level (rather than importing
``SessionLocal`` at each call site) so tests can point flushing at their isolated
engine, mirroring ``app/core/audit.py``.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import SessionLocal
from app.models.models import PackageFile, Share

logger = logging.getLogger("easyshare.counters")

# Sessionmaker used to persist buffered counters; overridable in tests.
counter_sessionmaker: sessionmaker[Session] = SessionLocal


class CounterBuffer:
    """Thread-safe accumulator of pending view/download increments.

    All mutation happens under a single lock so the sync request threadpool can
    increment concurrently while the background flusher drains atomically.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._views: dict[int, int] = defaultdict(int)
        self._downloads: dict[int, int] = defaultdict(int)

    def add_view(self, share_id: int, amount: int = 1) -> None:
        """Record ``amount`` pending views for a share."""
        with self._lock:
            self._views[share_id] += amount

    def add_downloads(self, file_ids: Iterable[int], amount: int = 1) -> None:
        """Record ``amount`` pending downloads for each of ``file_ids``."""
        with self._lock:
            for file_id in file_ids:
                self._downloads[file_id] += amount

    def pending_view(self, share_id: int) -> int:
        """Return the not-yet-flushed view delta for a share."""
        with self._lock:
            return self._views.get(share_id, 0)

    def pending_downloads(self, file_ids: Iterable[int]) -> dict[int, int]:
        """Return the not-yet-flushed download delta for each of ``file_ids``."""
        with self._lock:
            return {
                file_id: self._downloads.get(file_id, 0) for file_id in file_ids
            }

    def _drain(self) -> tuple[dict[int, int], dict[int, int]]:
        """Atomically remove and return all buffered deltas."""
        with self._lock:
            views = dict(self._views)
            downloads = dict(self._downloads)
            self._views.clear()
            self._downloads.clear()
            return views, downloads

    def _rebuffer(self, views: dict[int, int], downloads: dict[int, int]) -> None:
        """Put drained deltas back after a failed flush so counts aren't lost."""
        with self._lock:
            for share_id, delta in views.items():
                self._views[share_id] += delta
            for file_id, delta in downloads.items():
                self._downloads[file_id] += delta

    def flush(self) -> None:
        """Persist all buffered deltas in one transaction (one UPDATE per row).

        On any failure the drained deltas are re-buffered so they are retried on
        the next flush instead of being lost. Because the whole batch commits
        atomically, a failure never partially applies, so re-buffering cannot
        double-count.
        """
        views, downloads = self._drain()
        if not views and not downloads:
            return
        try:
            with counter_sessionmaker() as session:
                for share_id, delta in views.items():
                    if delta:
                        session.execute(
                            update(Share)
                            .where(Share.id == share_id)
                            .values(view_count=Share.view_count + delta)
                        )
                for file_id, delta in downloads.items():
                    if delta:
                        session.execute(
                            update(PackageFile)
                            .where(PackageFile.id == file_id)
                            .values(download_count=PackageFile.download_count + delta)
                        )
                session.commit()
        except Exception:
            self._rebuffer(views, downloads)
            logger.exception("counters.flush_failed")

    def reset(self) -> None:
        """Discard all buffered deltas (used between tests)."""
        with self._lock:
            self._views.clear()
            self._downloads.clear()


counter_buffer = CounterBuffer()
