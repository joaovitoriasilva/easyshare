"""Optional server-side crash reporting via GlitchTip (Sentry-compatible).

The FastAPI/Starlette integrations are auto-enabled by the SDK, so once
initialised, unhandled exceptions in request handlers (the 500s shaped by
``main.handle_unexpected_error``) are reported automatically. Enabled only when
``EASYSHARE_GLITCHTIP_DSN_BACKEND`` is set; otherwise this is a no-op and the SDK
is never imported.
"""

from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger("easyshare")

# Fraction of performance transactions to sample. Kept low so an always-on
# tracer cannot flood (or fill the disk of) the GlitchTip instance.
_TRACES_SAMPLE_RATE = 0.01


def init_sentry() -> bool:
    """Initialise Sentry for GlitchTip when a DSN is configured.

    Returns ``True`` when crash reporting was enabled, ``False`` when it is off
    (no DSN). Safe to call once at startup; the Python SDK talks to GlitchTip
    server-to-server, so no Content-Security-Policy change is required.
    """
    dsn = settings.glitchtip_dsn_backend.strip()
    if not dsn:
        return False

    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        # Tag events with the deployment environment so production noise can be
        # separated from development.
        environment=settings.environment,
        traces_sample_rate=_TRACES_SAMPLE_RATE,
        # GlitchTip does not support Sentry release-health "sessions".
        auto_session_tracking=False,
    )
    logger.info("Server-side crash reporting enabled (GlitchTip)")
    return True
