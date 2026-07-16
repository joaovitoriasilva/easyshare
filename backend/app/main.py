"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from safeuploads import FileValidationError

from app.api.routes import auth, packages, public, shares
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Secure file and package sharing API.",
)


@app.exception_handler(FileValidationError)
def handle_file_validation_error(
    request: Request, exc: FileValidationError
) -> JSONResponse:
    """Translate an upload rejected by safeuploads into an HTTP 400."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_prefix = "/api"
app.include_router(auth.router, prefix=api_prefix)
app.include_router(packages.router, prefix=api_prefix)
app.include_router(shares.router, prefix=api_prefix)
app.include_router(public.router, prefix=api_prefix)


@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    """Simple liveness probe."""
    return {"status": "ok"}
