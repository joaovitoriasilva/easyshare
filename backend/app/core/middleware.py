"""ASGI middleware assigning a request id and logging one line per request."""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings
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


class MaxBodySizeMiddleware:
    """Reject an over-sized request body before it is read or spooled to disk.

    Starlette spools the whole multipart body to a temporary file before a route
    (or its dependencies) runs, so an upload far larger than the per-file limit
    would otherwise touch disk before it could be refused. Rejecting up front on
    the declared ``Content-Length`` avoids that. A ``multipart/form-data`` body
    (a file upload) is allowed up to ``max_body_size``; a resumable-upload chunk
    (``application/offset+octet-stream``) up to ``chunk_max_body_size``; every
    other body (JSON and form APIs) is held to the much smaller
    ``json_max_body_size`` so a tiny endpoint can't be made to buffer a huge
    document in memory. Requests without a ``Content-Length`` (e.g. chunked
    transfer encoding) fall through to the per-file streaming cap enforced while
    the upload is written.
    """

    def __init__(
        self,
        app: ASGIApp,
        max_body_size: int,
        json_max_body_size: int | None = None,
        chunk_max_body_size: int | None = None,
    ) -> None:
        self.app = app
        self.max_body_size = max_body_size
        # Default the JSON cap to the multipart cap so single-argument
        # construction preserves the original single-limit behaviour.
        self.json_max_body_size = (
            json_max_body_size if json_max_body_size is not None else max_body_size
        )
        self.chunk_max_body_size = (
            chunk_max_body_size if chunk_max_body_size is not None else max_body_size
        )

    def _cap_for(self, content_type: str) -> int:
        """Return the size cap that applies to a body of ``content_type``."""
        if content_type.startswith("multipart/form-data"):
            return self.max_body_size
        if content_type.startswith("application/offset+octet-stream"):
            return self.chunk_max_body_size
        return self.json_max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        if content_length is not None:
            cap = self._cap_for(headers.get("content-type", ""))
            try:
                declared = int(content_length)
            except ValueError:
                declared = -1
            if declared > cap:
                response = JSONResponse(
                    {"detail": "Request body too large"},
                    status_code=413,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


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
            # Escalate a slow request to WARNING (keeping one line per request)
            # and tag it with ``slow`` so a log shipper can alert on latency
            # regressions without ingesting every access line.
            threshold = settings.slow_request_ms
            is_slow = threshold > 0 and duration_ms >= threshold
            logger.log(
                logging.WARNING if is_slow else logging.INFO,
                "request.completed",
                extra={
                    **extra,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "slow": is_slow,
                },
            )
        reset_request_id(token)
