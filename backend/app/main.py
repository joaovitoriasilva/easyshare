"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from safeuploads import FileValidationError
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.routes import admin, audit, auth, packages, public, shares
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.rate_limit import limiter, rate_limit_exceeded_handler

configure_logging()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Secure file and package sharing API.",
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


# Middleware runs outermost-first (reverse registration order). RequestContext
# is registered last so it wraps everything — every response gets a request id
# and one access-log line — while CORS stays outside SlowAPI so 429 responses
# still carry CORS headers.
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

api_prefix = "/api"
app.include_router(auth.router, prefix=api_prefix)
app.include_router(packages.router, prefix=api_prefix)
app.include_router(shares.router, prefix=api_prefix)
app.include_router(public.router, prefix=api_prefix)
app.include_router(audit.router, prefix=api_prefix)
app.include_router(admin.router, prefix=api_prefix)


@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    """Simple liveness probe."""
    return {"status": "ok"}
