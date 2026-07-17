"""ASGI middleware assigning a request id and logging one line per request."""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import reset_request_id, set_request_id

logger = logging.getLogger("easyshare.access")

# Liveness/readiness probes are hit constantly; logging them adds noise without
# value.
_QUIET_PATHS = frozenset({"/api/health", "/api/ready"})

_SECURITY_HEADERS: list[tuple[bytes, bytes]] = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (
        b"content-security-policy",
        b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        b"img-src 'self' data:; font-src 'self'; connect-src 'self'; "
        b"object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
    ),
]


class SecurityHeadersMiddleware:
    """Attach the security headers previously set by the nginx frontend proxy.

    Now that the backend serves the SPA directly (single-image deployment),
    these headers must be added here instead of in nginx.conf. Implemented as
    raw ASGI (not ``BaseHTTPMiddleware``) so it does not buffer streaming or
    ``FileResponse`` bodies.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [
                    *message.get("headers", []),
                    *_SECURITY_HEADERS,
                ]
            await send(message)

        await self.app(scope, receive, send_wrapper)


class RequestContextMiddleware:
    """Bind a request id, echo it back, and log request completion/failure.

    Implemented as raw ASGI (rather than ``BaseHTTPMiddleware``) so it does not
    buffer streaming/``FileResponse`` bodies or interfere with background tasks.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = Headers(scope=scope).get("x-request-id") or uuid4().hex
        # Stash on the ASGI scope so the outermost 500 handler can still read the
        # id after the contextvar below has been reset on the error path.
        scope.setdefault("state", {})["request_id"] = request_id
        token = set_request_id(request_id)
        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message["headers"] = [
                    *message.get("headers", []),
                    (b"x-request-id", request_id.encode("latin-1")),
                ]
            await send(message)

        client = scope.get("client")
        extra = {
            "http_method": scope.get("method"),
            "http_path": scope.get("path"),
            "client_ip": client[0] if client else None,
        }
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.exception(
                "request.failed",
                extra={**extra, "status_code": 500, "duration_ms": duration_ms},
            )
            reset_request_id(token)
            raise
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        if scope.get("path") not in _QUIET_PATHS:
            logger.info(
                "request.completed",
                extra={
                    **extra,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
        reset_request_id(token)
