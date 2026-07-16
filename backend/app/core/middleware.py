"""ASGI middleware assigning a request id and logging one line per request."""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import reset_request_id, set_request_id

logger = logging.getLogger("easyshare.access")

# Liveness probes are hit constantly; logging them adds noise without value.
_QUIET_PATHS = frozenset({"/api/health"})


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
