"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from safeuploads import FileValidationError
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import DbSession
from app.api.routes import (
    admin,
    admin_settings,
    audit,
    auth,
    packages,
    public,
    shares,
    uploads,
)
from app.core.config import settings
from app.core.logging import configure_logging, get_request_id
from app.core.middleware import (
    MaxBodySizeMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.rate_limit import (
    limiter,
    rate_limit_exceeded_handler,
    rate_limit_store_healthy,
)
from app.core.static import router as frontend_router
from app.core.tasks import (
    audit_retention_loop,
    counter_flush_loop,
    upload_session_prune_loop,
)
from app.services.counters import counter_buffer
from app.services.storage import storage

configure_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Start and cleanly stop background maintenance tasks.

    The audit-retention loop is only started when a positive
    ``audit_retention_days`` is configured; the counter-flush loop only when a
    positive ``counter_flush_interval_seconds`` is configured. On shutdown every
    started task is cancelled and a final counter flush persists any increments
    buffered since the last flush.
    """
    tasks: list[asyncio.Task[None]] = []
    if settings.audit_retention_days > 0:
        tasks.append(asyncio.create_task(audit_retention_loop()))
    if settings.counter_flush_interval_seconds > 0:
        tasks.append(asyncio.create_task(counter_flush_loop()))
    tasks.append(asyncio.create_task(upload_session_prune_loop()))
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        # Persist any counts buffered since the last flush; best-effort so a
        # storage error can never block a clean shutdown.
        with suppress(Exception):
            await asyncio.to_thread(counter_buffer.flush)


app = FastAPI(
    title=settings.app_name,
    version="0.4.0",
    description="Secure file and package sharing API.",
    lifespan=lifespan,
)

app.state.limiter = limiter
# Starlette types handlers as accepting bare Exception; the specific type is fine.
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[arg-type]


@app.exception_handler(FileValidationError)
def handle_file_validation_error(
    request: Request, exc: FileValidationError
) -> JSONResponse:
    """Translate an upload rejected by safeuploads into an HTTP 400."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


@app.exception_handler(Exception)
def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Return a JSON 500 that carries the request id for correlation.

    The traceback itself is logged as ``request.failed`` by
    ``RequestContextMiddleware``; this handler only shapes the client-facing
    response so it stays valid JSON and a caller can quote the request id when
    reporting a problem. The id is read from the ASGI scope (stashed by the
    middleware) because the request-id contextvar has already been reset by the
    time this outermost handler runs.
    """
    request_id = getattr(request.state, "request_id", None) or get_request_id()
    headers = {"X-Request-ID": request_id} if request_id else None
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "request_id": request_id},
        headers=headers,
    )


# Middleware runs outermost-first (reverse registration order). RequestContext
# is registered last so it wraps everything — every response gets a request id
# and one access-log line — while CORS stays outside SlowAPI so 429 responses
# still carry CORS headers. SecurityHeaders is registered first (innermost) so
# it still stamps the SPA/static responses served by frontend_router below.
# MaxBodySize is registered before all of them so it ends up innermost of the
# user middleware: it turns away an over-sized upload just before routing (and
# thus before the endpoint reads/spools the multipart body), while its 413 still
# flows back out through the request-id and security-header middleware.
app.add_middleware(
    MaxBodySizeMiddleware,
    max_body_size=settings.max_request_body_size,
    json_max_body_size=settings.max_json_body_size,
    chunk_max_body_size=settings.chunk_max_body_size,
)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Auth uses a bearer token in the Authorization header (not cookies), so
    # credentialed CORS is unnecessary and would needlessly widen exposure.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

api_prefix = "/api"
app.include_router(auth.router, prefix=api_prefix)
app.include_router(packages.router, prefix=api_prefix)
app.include_router(uploads.router, prefix=api_prefix)
app.include_router(shares.router, prefix=api_prefix)
app.include_router(public.router, prefix=api_prefix)
app.include_router(audit.router, prefix=api_prefix)
app.include_router(admin.router, prefix=api_prefix)
app.include_router(admin_settings.router, prefix=api_prefix)


@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    """Simple liveness probe: process is up. Does not check dependencies."""
    return {"status": "ok"}


@app.get("/api/ready", tags=["health"])
def ready(db: DbSession) -> dict[str, str]:
    """Readiness probe: the app can actually serve traffic (DB + storage)."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from exc
    try:
        storage.check_writable()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage unavailable",
        ) from exc
    if not rate_limit_store_healthy():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate-limit store unavailable",
        )
    return {"status": "ready"}


# Single-image deployment: the built frontend SPA is served directly by this
# app (see app/core/static.py). Registered last (after every API router)
# because its catch-all "/{full_path:path}" route would otherwise shadow
# every other route.
app.include_router(frontend_router)
