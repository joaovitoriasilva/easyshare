"""Centralized rate limiting for the EasyShare API.

A single :data:`limiter` instance is shared by every router. ``SlowAPIMiddleware``
applies the :data:`DEFAULT` limit to all routes automatically; sensitive
endpoints add a tighter cap with ``@limiter.limit(SENSITIVE)``.

The key function buckets authenticated callers by a hash of their bearer token
(so each session is limited independently, even behind a shared NAT) and falls
back to the client IP for anonymous callers. For that IP to reflect the real
client behind nginx, uvicorn must run with
``--proxy-headers --forwarded-allow-ips=<proxy>`` so ``request.client.host`` is
derived from a trusted ``X-Forwarded-For`` rather than a spoofable header.
"""

from __future__ import annotations

import hashlib
import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import Response

from app.core.config import settings

logger = logging.getLogger(__name__)

#: Baseline limit applied to every route via ``SlowAPIMiddleware``.
DEFAULT = "120/minute"
#: Sensitive operations: login, registration and restricted-share unlock.
SENSITIVE = "10/minute"
#: Single-file downloads: heavier than a normal API call but still cheap.
DOWNLOAD = "60/minute"
#: Expensive operations that build a zip archive on the fly. Kept low because
#: each one holds a worker thread and can produce a multi-gigabyte file.
EXPENSIVE = "10/minute"


def rate_limit_key(request: Request) -> str:
    """Bucket by a hashed bearer token when present, else by client IP."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer ") and len(auth) > 7:
        digest = hashlib.sha256(auth[7:].encode()).hexdigest()[:16]
        return f"user:{digest}"
    return get_remote_address(request)


limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=[DEFAULT],
    enabled=settings.rate_limit_enabled,
    storage_uri=settings.rate_limit_storage_uri,
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Return a JSON 429 with ``Retry-After``/``X-RateLimit-*`` headers."""
    logger.warning(
        "Rate limit exceeded: %s on %s %s",
        rate_limit_key(request),
        request.method,
        request.url.path,
    )
    response: Response = JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please try again later."},
    )
    # ``view_rate_limit`` is populated by slowapi before the handler runs.
    # Header injection uses a private helper and is best-effort only, so a
    # failure there must never break the 429 response itself.
    try:
        response = request.app.state.limiter._inject_headers(
            response, request.state.view_rate_limit
        )
    except Exception as err:  # informational headers only
        logger.debug("Failed to inject rate-limit headers: %s", err)
    return response
