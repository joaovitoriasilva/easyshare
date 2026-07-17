"""Structured logging configuration and request-scoped context.

Logging is emitted to stdout (12-factor) either as human-readable lines
(``log_format=console``) or single-line JSON (``log_format=json``) for shippers.
A :class:`RequestIdFilter` stamps every record with the id bound by the request
middleware so application, access and audit logs can be correlated.
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from logging.config import dictConfig
from typing import Any

from app.core.config import settings

# Request id bound for the lifetime of a single HTTP request by the middleware.
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def set_request_id(value: str | None) -> Token[str | None]:
    """Bind ``value`` as the current request id; returns a reset token."""
    return _request_id.set(value)


def reset_request_id(token: Token[str | None]) -> None:
    """Restore the request id to its previous value."""
    _request_id.reset(token)


def get_request_id() -> str | None:
    """Return the request id bound to the current context, if any."""
    return _request_id.get()


def mask_email(value: str) -> str:
    """Partially redact an email address for logging (``a***@e***.com``).

    Leaves non-email strings unchanged. Used to keep personally identifiable
    addresses out of stdout logs (which are often shipped to third-party
    aggregators) while the access-controlled audit table keeps the full value.
    """
    local, sep, domain = value.partition("@")
    if not sep:
        return value

    def _keep_initial(part: str) -> str:
        return f"{part[0]}***" if part else "***"

    name, dot, tld = domain.rpartition(".")
    masked_domain = f"{_keep_initial(name)}.{tld}" if dot else _keep_initial(domain)
    return f"{_keep_initial(local)}@{masked_domain}"


# Standard LogRecord attributes; anything else on a record is an ``extra`` field
# and is included as-is in JSON output.
_RESERVED = frozenset(
    {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "taskName", "message", "asctime", "request_id",
    }
)


class RequestIdFilter(logging.Filter):
    """Attach the current request id to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Configure root, application and uvicorn loggers from settings."""
    formatter = "json" if settings.log_format.lower() == "json" else "console"
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"request_id": {"()": RequestIdFilter}},
            "formatters": {
                "json": {"()": JsonFormatter},
                "console": {
                    "format": (
                        "%(asctime)s %(levelname)-8s [%(request_id)s] "
                        "%(name)s: %(message)s"
                    ),
                },
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": formatter,
                    "filters": ["request_id"],
                }
            },
            "loggers": {
                "easyshare": {
                    "level": settings.log_level,
                    "handlers": ["default"],
                    "propagate": False,
                },
                "uvicorn": {
                    "level": "INFO",
                    "handlers": ["default"],
                    "propagate": False,
                },
                "uvicorn.error": {
                    "level": "INFO",
                    "handlers": ["default"],
                    "propagate": False,
                },
                # The request middleware emits structured access logs; keep
                # uvicorn's redundant access log quiet.
                "uvicorn.access": {
                    "level": "WARNING",
                    "handlers": ["default"],
                    "propagate": False,
                },
            },
            "root": {"level": settings.log_level, "handlers": ["default"]},
        }
    )
